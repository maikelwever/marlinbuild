#!/usr/bin/env python3

import os
import shutil

from configparser import ConfigParser
from glob import glob
from subprocess import Popen, PIPE
from pathlib import Path
from tempfile import TemporaryDirectory


BASE_DIR = Path(os.path.abspath('.'))


class App:
    marlin_version = '1.1.9'

    def __init__(self):
        manufacturers_inis = glob(str(BASE_DIR / 'configs' / '*.ini'))
        self.manufacturers = dict()

        for ini_file in manufacturers_inis:
            parser = ConfigParser()
            parser.read(ini_file)
            manufacturer_name = os.path.splitext(os.path.basename(ini_file))[0]
            self.manufacturers[manufacturer_name] = {s: dict(parser.items(s)) for s in parser.sections()}

        self.marlin_dir = BASE_DIR / 'marlin'
        self.version_string, self.marlin_dump_tar = self.init_marlin_dir()

        self.output_dir = BASE_DIR / 'output'
        if not self.output_dir.exists():
            self.output_dir.mkdir()

    def init_marlin_dir(self):
        if not self.marlin_dir.exists():
            s = Popen(['git', 'clone', 'https://github.com/MarlinFirmware/Marlin', self.marlin_dir])
            s.communicate()
        else:
            s = Popen(['git', 'fetch'], cwd=self.marlin_dir)
            s.communicate()

        s = Popen(['git', 'checkout', self.marlin_version], cwd=self.marlin_dir)
        s.communicate()

        s = Popen(['git', 'rev-parse', '--short', 'HEAD'], stdout=PIPE, cwd=self.marlin_dir)
        stdout, stderr = s.communicate()
        git_commit_short = stdout.decode().strip()

        if self.marlin_version == git_commit_short:
            version_string = self.marlin_version
        else:
            version_string = '{}-{}'.format(self.marlin_version, git_commit_short)

        dump_output = os.path.abspath('marlin-{}.tar'.format(version_string))
        s = Popen(['git', 'archive', '--format', 'tar', '--output', dump_output, 'HEAD'], cwd=self.marlin_dir)
        s.communicate()

        return version_string, dump_output

    def build_marlin(self, manufacturer, printer, printer_dir, printer_config):
        with TemporaryDirectory() as build_dir:
            print('Building Marlin for {} {} in {}'.format(manufacturer, printer, build_dir))

            s = Popen(['tar', 'xf', self.marlin_dump_tar], cwd=build_dir)
            s.communicate()

            if printer_config.get('upstream_conf'):
                config_dir = self.marlin_dir / 'Marlin' / 'example_configurations' / printer_config['upstream_conf']
            elif printer_config.get('conf'):
                config_dir = os.path.abspath(printer_config['conf'])
            else:
                config_dir = None

            if config_dir:
                s = Popen(['bash', '-c', 'cp {}/* {}/Marlin/'.format(config_dir, build_dir)])
                s.communicate()

            env = printer_config.get('env', 'megaatmega2560')
            s = Popen(['platformio', 'run', '-e', env], cwd=build_dir, stdout=PIPE, stderr=PIPE)
            stdout, stderr = s.communicate()

            with open(printer_dir / '{}.stdout.log'.format(self.version_string), 'wb') as f:
                f.write(stdout)

            with open(printer_dir / '{}.stderr.log'.format(self.version_string), 'wb') as f:
                f.write(stderr)

            output_file = printer_dir / '{}_{}_{}.hex'.format(manufacturer, printer, self.version_string)
            shutil.copy(Path(build_dir) / '.pioenvs' / env / 'firmware.hex', output_file)
            return output_file

    def run(self):
        built_files = []
        for manufacturer, printers in self.manufacturers.items():
            manuf_path = self.output_dir / manufacturer
            if not manuf_path.exists():
                manuf_path.mkdir()

            for printer, printer_config in printers.items():
                printer_dir = manuf_path / printer
                if not printer_dir.exists():
                    printer_dir.mkdir()

                result_file = self.build_marlin(manufacturer, printer, printer_dir, printer_config)
                built_files.append(result_file)

        os.remove(self.marlin_dump_tar)

        for i in built_files:
            print(i)

        # TODO: make shiney html pages


if __name__ == '__main__':
    App().run()
