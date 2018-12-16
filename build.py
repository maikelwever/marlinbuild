#!/usr/bin/env python3

import os
import shutil

from configparser import ConfigParser
from glob import glob
from subprocess import Popen, PIPE
from pathlib import Path
from tempfile import TemporaryDirectory


BASE_DIR = Path(os.path.abspath('.'))
MARLIN_VERSION = "1.1.9"


def init_marlin_dir(marlin_dir):
    if not marlin_dir.exists():
        s = Popen(['git', 'clone', 'https://github.com/MarlinFirmware/Marlin', marlin_dir])
        s.communicate()
    else:
        s = Popen(['git', 'fetch'], cwd=marlin_dir)
        s.communicate()

    s = Popen(['git', 'checkout', MARLIN_VERSION], cwd=marlin_dir)
    s.communicate()

    s = Popen(['git', 'rev-parse', '--short', 'HEAD'], stdout=PIPE, cwd=marlin_dir)
    stdout, stderr = s.communicate()
    git_commit_short = stdout.decode().strip()

    if MARLIN_VERSION == git_commit_short:
        version_string = MARLIN_VERSION
    else:
        version_string = '{}-{}'.format(MARLIN_VERSION, git_commit_short)

    dump_output = os.path.abspath("marlin-{}.tar".format(version_string))
    s = Popen(['git', 'archive', '--format', 'tar', '--output', dump_output, 'HEAD'], cwd=marlin_dir)
    s.communicate()

    return version_string, dump_output


def build_marlin(printer_dir, printer_config, marlin_dir, version_string, marlin_dump_tar):
    with TemporaryDirectory() as build_dir:
        print(build_dir)
        s = Popen(['tar', 'xf', marlin_dump_tar], cwd=build_dir)
        s.communicate()

        if printer_config.get('upstream_conf'):
            config_dir = marlin_dir / 'Marlin' / 'example_configurations' / printer_config['upstream_conf']
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

        with open(printer_dir / '{}.stdout.log'.format(version_string), 'wb') as f:
            f.write(stdout)

        with open(printer_dir / '{}.stderr.log'.format(version_string), 'wb') as f:
            f.write(stderr)

        output_file = printer_dir / '{}.hex'.format(version_string)
        shutil.copy(Path(build_dir) / '.pioenvs' / env / 'firmware.hex', output_file)
        return output_file


def main():
    manufacturers_inis = glob(str(BASE_DIR / "*.ini"))
    manufacturers = dict()

    for ini_file in manufacturers_inis:
        parser = ConfigParser()
        parser.read(ini_file)
        manufacturer_name = os.path.splitext(os.path.basename(ini_file))[0]
        manufacturers[manufacturer_name] = {s: dict(parser.items(s)) for s in parser.sections()}

    marlin_dir = BASE_DIR / "marlin"
    version_string, marlin_dump_tar = init_marlin_dir(marlin_dir)

    output_dir = BASE_DIR / "output"
    if not output_dir.exists():
        output_dir.mkdir()

    built_files = []

    for manufacturer, printers in manufacturers.items():
        manuf_path = output_dir / manufacturer
        if not manuf_path.exists():
            manuf_path.mkdir()

        for printer, printer_config in printers.items():
            printer_dir = manuf_path / printer
            if not printer_dir.exists():
                printer_dir.mkdir()

            result_file = build_marlin(
                printer_dir, printer_config,
                marlin_dir, version_string, marlin_dump_tar,
            )
            built_files.append(result_file)

    os.remove(marlin_dump_tar)

    for i in built_files:
        print(i)


if __name__ == "__main__":
    main()
