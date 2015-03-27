==============
OpenVNFManager
==============

OpenVNFManager enables NFV service orchestration on openstack platform

* git clone --recursive https://github.com/TCS-TelcoCloud/OpenVNFManager.git

* It has 3 components::

    $ vnfsvc 
    $ vnfManager
    $ python-vnfsvcclient

vnfsvc
-------

* Runs as a service [ similar to openstack neutron etc ] on the controller node
  It implements server side for vnfsvcclient and HEAT

vnfManager
-----------

Interfaces with VNFs and vnfsvc for configuration and lifecycle management of virtual network functions
In the current setup init is the only supported lifecycle event

python-vnfsvcclient
--------------------

* This is a client for the Vnfsvc API

After installing vnfsvc, python-vnfsvcclient and HEAT updates, run the setup as detailed in vnfsvc_examples
