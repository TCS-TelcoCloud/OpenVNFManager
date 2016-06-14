=================================
Python bindings to the Vnfsvc API
=================================

* This is a client for the Vnfsvc API

  To install::

    $ git clone https://github.com/TCS-TelcoCloud/OpenVNFManager.git
    $ python setup.py install

Command-line API
-----------------

* You'll find complete command usage the shell by running::

    $ vnfsvc help

* Create, List, Show and Delete is supported for now
  Usage of the operations supported can be find by appending "-h"::

    $ Ex: vnfsvc service-create -h 

* Example command for the create operation is given below::

    $ vnfsvc service-create --name webservice --qos Silver --networks mgmt-if='fce9ee06-a6cd-4405-ba0f-d8491dd38e2a' --networks public='b481ac9c-19bb-4216-97b5-25f5bd8be4ae' --networks private='6458b56a-a6a2-42d5-8634-bdec253edf4e' --router 'router' --subnets mgmt-if='0c8ccdf2-3808-462c-ab1e-1e1b621b0324' --subnets public='baf8bae2-3e4c-4b8b-bdb9-964fb1594203' --subnets private='ad09ac00-c4d7-473f-94ec-2ad22153d1ca'
    $ Networks, subnets and router given in the command should exist before

* Command for the list operation is as given below::

    $ vnfsvc service-list <service-id>

* Command for the show operation is as given below::

    $ vnfsvc service-show <service-id>

* Command for the delete operation is as given below::

    $ vnfsvc service-delete <service-id>

* After installing vnfsvc, python-vnfsvcclient and HEAT updates, run the setup as detailed in vnfsvc_examples
