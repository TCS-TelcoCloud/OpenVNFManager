=======
VNFSVC
=======

OpenVNFManager enables NFV service orchestration on openstack platform

* Runs as a service [ similar to openstack neutron etc ] on the controller node
  It implements server side for vnfsvcclient and HEAT

  To install::

    $ git clone https://github.com/TCS-TelcoCloud/OpenVNFManager.git
    $ python setup.py install

* Check::

    $ api-paste.ini,  rootwrap.conf,  rootwrap.d,  templates.json,  vnfsvc.conf exists in /etc/vnfsvc/ [ on RedHat Linux/Centos7/Fedora ]
    $ passwords and urls of the openstack services in /etc/vnfsvc/vnfsvc.conf

* Create keystone endpoints::

    $ keystone service-create --name vnfsvc --type vnfservice --description "VNF service"
    $ keystone endpoint-create --region RegionOne --service-id <vnfsvc_service_id> --publicurl "http://<your_ip>:9010" --internalurl "http://<your_ip>:9010" --adminurl "http://<your_ip>:9010"
    $ keystone user-create --tenant-id <service_tenant_id> --name vnfsvc --pass <passsword>
    $ keystone user-role-add --user-id <vnfsvc_user_id> --tenant-id <service_tenant_id> --role-id <admin_role_id>
  
* Execute the following commands for database configuration::

    $ create database vnfsvc; (MYSQL)
    $ grant all privileges on vnfsvc.* to 'vnfsvc'@'localhost' identified by <database password>; (MYSQL)
    $ grant all privileges on vnfsvc.* to 'vnfsvc'@'%' identified by <database password>; (MYSQL)
    $ vnfsvc-db-manage --config-file /etc/vnfsvc/vnfsvc.conf upgrade head
    $ mkdir /var/log/vnfsvc

* Run with the following command to start the server::

    $ python /usr/bin/vnfsvc-server  --config-file /etc/vnfsvc/vnfsvc.conf --log-file /var/log/vnfsvc/server.log 
