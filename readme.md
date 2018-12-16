Prebuilt Marlin
===============

This project aims to provide prebuilt binaries of Marlin for various 3d printers.

Printer configuration is pulled from upstream Marlin.


How to use
----------

Get Python 3 installed, and run `python -m marlinbuild <channel> <git_checkout>`.

The channel is the frontend-name of this release. Recommended options: stable, bugfix-1.1.x, bugfix-2.0.x.

The git_checkout is the git ref to use. This can be a branch, tag, or commit id.

If you want to fiddle with the templates, pass '--pages-only' to stop building.


Usage with Docker
-----------------

Create a folder called `output`. It will be used inside the container to put the binaries and HTML in. 

Prepare image (one-time): `docker build -t marlinbuild .`

To build: `docker --rm -it -v "$PWD/output:/home/builduser/output/" marlinbuild <channel> <git_checkout>`

If you want to build in RAM: `docker --rm -it --tmpfs /tmp -v "$PWD/output:/home/builduser/output/" marlinbuild <channel> <git_checkout>`


How it works
------------

In the `configs` folder, there are several .ini files describing how to build a binary for a given printer.

The `marlinbuild` folder contains Python code that (in this order):

 - reads the .ini files
 - pulls the requested Marlin version
 - does a build in a temporary directory
 - generates static HTML with links to the binaries
