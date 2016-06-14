==========
VNFManager
==========

Interfaces with VNFs and vnfsvc for configuration and lifecycle management of virtual network functions
In the current setup init is the only supported lifecycle event

* Sample descriptors and howTo are provided in vnfsvc_examples folder. It has::

    $ NSD 
    $ VNFD
    $ HEAT template
    $ README for running the installation

* After installing vnfsvc, python-vnfsvcclient and HEAT updates, run the setup as detailed in vnfsvc_examples

* To install::

    $ git clone https://github.com/TCS-TelcoCloud/vnfmanager.git
    $ python setup.py install
