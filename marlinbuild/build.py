#!/usr/bin/env python3

import hashlib
import json
import os
import shutil

from argparse import ArgumentParser
from collections import OrderedDict, defaultdict
from configparser import ConfigParser
from glob import glob
from subprocess import Popen, PIPE
from pathlib import Path
from tempfile import TemporaryDirectory
from time import time

from jinja2 import Environment, PackageLoader, select_autoescape

BASE_DIR = Path(os.path.abspath('.'))

env = Environment(
    loader=PackageLoader('marlinbuild', 'templates'),
    autoescape=select_autoescape(['html', 'xml'])
)


class App:
    def __init__(self, channel, git_checkout, manufacturer=None, printer=None):
        self.channel = channel
        self.git_checkout = git_checkout

        self.limit_manufacturer = manufacturer
        if self.limit_manufacturer:
            self.limit_manufacturer = self.limit_manufacturer.lower()

        self.limit_printer = printer
        if self.limit_printer:
            self.limit_printer = self.limit_printer.lower()

        manufacturers_inis = glob(str(BASE_DIR / 'configs' / '*.ini'))
        manufacturers = dict()

        for ini_file in manufacturers_inis:
            parser = ConfigParser()
            parser.read(ini_file)
            manufacturer_name = os.path.splitext(os.path.basename(ini_file))[0]
            manufacturers[manufacturer_name] = OrderedDict(
                sorted({s: dict(parser.items(s)) for s in parser.sections()}.items(), key=lambda x: x[0].lower()))

        self.manufacturers = OrderedDict(sorted(manufacturers.items(), key=lambda x: x[0].lower()))

        self.output_dir = BASE_DIR / 'output'
        if not self.output_dir.exists():
            self.output_dir.mkdir()

    def init_marlin_dir(self):
        if not self.marlin_dir.exists():
            s = Popen(['git', 'clone', 'https://github.com/MarlinFirmware/Marlin', str(self.marlin_dir)])
            s.communicate()
        else:
            s = Popen(['git', 'fetch'], cwd=str(self.marlin_dir))
            s.communicate()

        s = Popen(['git', 'checkout', self.git_checkout], cwd=str(self.marlin_dir))
        s.communicate()

        s = Popen(['git', 'rev-parse', '--short', 'HEAD'], stdout=PIPE, cwd=str(self.marlin_dir))
        stdout, stderr = s.communicate()
        git_commit_short = stdout.decode().strip()

        if self.channel == self.git_checkout:
            version_string = '{}-{}'.format(self.channel, git_commit_short)
        elif self.git_checkout == git_commit_short:
            version_string = '{}-{}'.format(self.channel, git_commit_short)
        else:
            version_string = '{}-{}-{}'.format(self.channel, self.git_checkout, git_commit_short)

        dump_output = os.path.abspath('marlin-{}.tar'.format(version_string))
        s = Popen(['git', 'archive', '--format', 'tar', '--output', dump_output, 'HEAD'], cwd=str(self.marlin_dir))
        s.communicate()

        self.build_info_blob_base = dict(
            channel=self.channel,
            git_checkout=self.git_checkout,
            version_string=version_string,
            git_commit_short=git_commit_short,
        )

        return version_string, dump_output

    def build_marlin(self, manufacturer, printer, printer_dir, printer_config):
        if printer_config.get('marlin_2_only') and not ('2.' in self.channel or '2.' in self.git_checkout):
            print('Not building {} {} for Marlin 1.x.x series, marked as 2.x.x only.'.format(manufacturer, printer))
            return

        output_filename = 'Marlin_{}_{}_{}'.format(manufacturer, printer, self.version_string)
        output_file = printer_dir / '{}.hex'.format(output_filename)
        if output_file.exists():
            print('Marlin already built for {} {}'.format(manufacturer, printer))
            return

        with TemporaryDirectory() as build_dir:
            print('Building Marlin for {} {} in {}'.format(manufacturer, printer, build_dir))

            s = Popen(['tar', 'xf', str(self.marlin_dump_tar)], cwd=build_dir)
            s.communicate()

            if printer_config.get('upstream_conf'):
                if '2.' in self.channel:
                    config_dir = self.marlin_dir / 'Marlin' / 'src' / \
                        'config' / 'examples' / printer_config['upstream_conf']
                else:
                    config_dir = self.marlin_dir / 'Marlin' / 'example_configurations' \
                        / printer_config['upstream_conf']

            elif printer_config.get('conf'):
                config_dir = os.path.abspath(printer_config['conf'])
            else:
                config_dir = None

            if config_dir:
                s = Popen(['bash', '-c', 'cp {}/* {}/Marlin/'.format(config_dir, build_dir)])
                s.communicate()

            env = printer_config.get('env', 'megaatmega2560')
            s = Popen(['bash', '-cx', 'date && platformio run -e {} 2>&1 && sha256sum .pioenvs/*/firmware.hex'.format(env)], cwd=build_dir, stdout=PIPE)  # noqa
            stdout, stderr = s.communicate()

            with open(str(printer_dir / '{}.txt'.format(output_filename)), 'wb') as f:
                f.write(stdout)

            if not s.returncode == 0:
                print("Build failed :(")
                print(stdout.decode())
                return

            shutil.copy(str(Path(build_dir) / '.pioenvs' / env / 'firmware.hex'), str(output_file))

            output_hash = hashlib.sha256()
            with open(str(output_file), 'rb') as f:
                for block in iter(lambda: f.read(4096), b''):
                    output_hash.update(block)

            build_info = self.build_info_blob_base
            build_info.update(dict(
                timestamp=int(time()),
                manufacturer=manufacturer,
                printer=printer,
                filename_base=str(output_filename),
                sha256sum=output_hash.hexdigest(),
            ))

            with open(str(printer_dir / '{}.json'.format(output_filename)), 'w') as f:
                json.dump(build_info, f)

            return output_file

    def render_pages(self):
        print("Rendering static pages")

        index_template = env.get_template('index.html')
        manufacturer_template = env.get_template('manufacturer.html')
        printer_template = env.get_template('printer.html')

        with open(str(self.output_dir / 'index.html'), 'w') as f:
            f.write(index_template.render(
                manufacturers=self.manufacturers,
            ))

        builds = {}

        for manufacturer, printers in self.manufacturers.items():
            manuf_path = self.output_dir / manufacturer.lower()
            if not manuf_path.exists():
                continue

            builds[manufacturer] = {}
            for printer, printer_config in printers.items():
                printer_dir = manuf_path / printer.lower()
                if not printer_dir.exists():
                    continue

                builds[manufacturer][printer] = defaultdict(list)
                for build_info in glob(str(printer_dir / '*.json')):
                    with open(build_info, 'r') as f:
                        data = json.load(f)

                    builds[manufacturer][printer][data.get('channel', 'unknown')].append(data)

                for channel in builds[manufacturer][printer].keys():
                    builds[manufacturer][printer][channel] = list(reversed(sorted(
                        builds[manufacturer][printer][channel], key=lambda x: x.get('timestamp', 0)
                    )))

                builds[manufacturer][printer] = dict(sorted(builds[manufacturer][printer].items(),
                                                     key=lambda x: '!' if x[0] == 'stable' else x[0]))

                with open(str(printer_dir / 'index.html'), 'w') as f:
                    f.write(printer_template.render(
                        manufacturer=manufacturer,
                        printer=printer,
                        printer_config=printer_config,
                        builds=builds[manufacturer][printer],
                    ))

            with open(str(manuf_path / 'index.html'), 'w') as f:
                f.write(manufacturer_template.render(
                    manufacturer=manufacturer,
                    printers=printers,
                    builds=builds[manufacturer],
                ))

    def run(self):
        self.marlin_dir = BASE_DIR / 'marlin'
        self.version_string, self.marlin_dump_tar = self.init_marlin_dir()

        build_counter = 0
        for manufacturer, printers in self.manufacturers.items():
            if self.limit_manufacturer and manufacturer.lower() != self.limit_manufacturer:
                continue

            manuf_path = self.output_dir / manufacturer.lower()
            if not manuf_path.exists():
                manuf_path.mkdir()

            for printer, printer_config in printers.items():
                if self.limit_printer and printer.lower() != self.limit_printer:
                    continue

                printer_dir = manuf_path / printer.lower()
                if not printer_dir.exists():
                    printer_dir.mkdir()

                result = self.build_marlin(manufacturer, printer, printer_dir, printer_config)
                if result:
                    build_counter += 1

        os.remove(self.marlin_dump_tar)

        if build_counter > 0:
            self.render_pages()


def main():
    parser = ArgumentParser()
    parser.add_argument('--manufacturer', help='Limit builds to this manufacturer')
    parser.add_argument('--printer', help='Limit builds to this printer')
    parser.add_argument('--pages-only', help='Only update the pages', action='store_true')
    parser.add_argument('--force-render-pages', help='Render pages even if there are no builds', action='store_true')
    parser.add_argument('channel', help='Name of this channel (stable/bugfix/2.0/etc)')
    parser.add_argument('git_checkout', help='Git commit/tag/branch to use (defaults to channel)')

    args = parser.parse_args()
    app = App(args.channel, args.git_checkout, manufacturer=args.manufacturer, printer=args.printer)

    if args.pages_only:
        app.render_pages()
    else:
        app.run()
        if args.force_render_pages:
            app.render_pages()


if __name__ == '__main__':
    main()
