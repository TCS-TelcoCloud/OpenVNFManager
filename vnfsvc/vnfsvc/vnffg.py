
import random


from vnfsvc.client import client

from vnfsvc.openstack.common import log as logging
from vnfsvc.common.yaml.nsdparser import NetworkParser
from vnfsvc.common.yaml.vnfdparser import VNFParser

from vnfsvc.common import exceptions
from vnfsvc.openstack.common import excutils
from vnfsvc.client import utils as ovs_utils

DEFAULT_OVS_VSCTL_TIMEOUT = 10
BASE_MAC_ADDRESS = "00:5a:4b:00:00:00"


class ForwardingGraph():
    #TODO: (tcs) Need clean up
    def __init__(self, nsd_template, vnfds):
        self.nsd_template = nsd_template
        self.vnfds = vnfds
        self.neutronclient = client.NeutronClient()
        self.br_name = "br-int"
        self.vsctl_timeout = DEFAULT_OVS_VSCTL_TIMEOUT
        self.instance_details = dict()
        self.ovs_port_list = list()
        self.forwarding_path = list()


    def configure_forwarding_graph(self):
        self.get_ns_config_details()
        self._modify_iptables()
        #self.forwarding_path = NetworkParser().get_forwarding_graph(self.nsd_template)
        #port_list = list()
        #for order in range(0, len(self.forwarding_path)-1):
        #    self.network_forwarding(order, order+1)
        #for order in range(len(self.forwarding_path)-1,0):
        #    self.network_forwarding(order, order-1)


    def vdu_network_forwarding(self,vnf_dict1,vnf_dict2):
        if vnf_dict1['subnet_id'] == vnf_dict2['subnet_id']:
            if vnf_dict1['is_gateway']:
                pass
        else:
            pass


    def network_forwarding(self, order1, order2):
        vnf = self.forwarding_path[order1]['name'].split(":")[0]
        vnf_peer = self.forwarding_path[order2]['name'].split(":")[0]

        vnf_details = self.forwarding_path[order1]
        vnf_peer_details = self.forwarding_path[order2]

        if vnf != vnf_peer:
            if vnf_details['type'] == "vnf" or "connection-point" in vnf_details.keys():
                vnf_cp = self.instance_details[vnf][vnf_details['connection-point']]

                if vnf_peer_details['type'] == "vnf" or "connection-point" in vnf_peer_details.keys():
                    vnf_peer_cp = self.instance_details[vnf_peer][vnf_peer_details['connection-point']]
                else:
                    vnf_peer_cp = self.instance_details[vnf_peer]

            else:
                vnf_cp = self.instance_details[vnf]
                if vnf_peer_details['type'] == "vnf" or "connection-point" in vnf_peer_details.keys():
                    vnf_peer_cp = self.instance_details[vnf_peer][vnf_peer_details['connection-point']]
                else:
                    vnf_peer_cp = self.instance_details[vnf_peer]

            self.vdu_network_forwarding(vnf_cp, vnf_peer_cp)


    def _populate_details(self, vdu_details, port, subnets, ports):
        vdu_details['subnet_id'] = port['fixed_ips'][0]['subnet_id']
        vdu_details['mac_address'] = port['mac_address']
        vdu_details['network_id'] = port['network_id']
        vdu_details['ovs_port'] = self.get_port_ofport(vdu_details['vm_interface'])
        for subnet in subnets:
            if subnet['id'] == vdu_details['subnet_id']:
                vdu_details['gateway_ip'] = subnet['gateway_ip']
        for port in ports:
            if vdu_details['gateway_ip'] == port['fixed_ips'][0]['ip_address']:
                vdu_details['is_gateway'] = True

        return vdu_details


    def get_ns_config_details(self):
        subnets = self.neutronclient.get_subnets()
        ports = self.neutronclient.get_ports()

        for vnfd in self.nsd_template['vnfds']:
            self.instance_details[vnfd] = dict()
            for vdu in self.nsd_template['vnfds'][vnfd]:
                vdu_name = vnfd + ":" + vdu
                for instance in self.vnfds[vnfd]['vdus'][vdu]['instances']:
                    instance_networks = instance.networks
                    for k,v in instance_networks.iteritems():
                        vdu_details = dict()
                        vdu_details['name'] = instance.name
                        vdu_details['hostname'] = instance.__dict__['OS-EXT-SRV-ATTR:host']
                        vdu_details['is_gateway'] = False
                        for port in ports:
                            if v[0] == port['fixed_ips'][0]['ip_address']:
                                vdu_details['port-id'] = port['id'] 
                                vdu_details['vm_interface'] = "qvo"+port['id'][:11]
                                vdu_details = self._populate_details(vdu_details, port, subnets, ports)
                                break
                        for key1,value1 in self.nsd_template['vdus'][vdu_name]['networks'].iteritems():
                            if vdu_details['subnet_id'] == value1['subnet-id']:
                                #self.instance_details[vnfd][key1] = vdu_details
                                if not key1 in self.instance_details[vnfd].keys():
                                    self.instance_details[vnfd][key1] = []
                                self.instance_details[vnfd][key1].append(vdu_details)

                if self.nsd_template['router']:
                   for key in self.nsd_template['router']:
                       router_details = dict()
                       port_id = self.nsd_template['router'][key]['interface']['port_id']
                       port_details = self.neutronclient.get_port(port_id)
                       router_details['vm_interface'] = "qr-"+port_details['id']
                       router_details = self._populate_details(router_details, port_details, subnets, ports)
                       self.instance_details[key] = router_details
        return self.instance_details

    def _modify_iptables(self):
        ipt_cmd_list = []
        port = ""
        for vdu in self.instance_details.keys():
            if vdu != "apn-router-gateway":
                for iface in self.instance_details[vdu].keys():
                    if iface != "" :
                        for vm in self.instance_details[vdu][iface]:
                            port = str(vm['port-id'])
                            self.neutronclient.update_port(port, \
                                   body={"port": {"allowed_address_pairs": [{"ip_address": "0.0.0.0/0"}]}})

    def run_vsctl(self, args, check_error=False):
        full_args = ["sudo", "ovs-vsctl", "--timeout=%d" % self.vsctl_timeout] + args
        try:
            return ovs_utils.execute(full_args, root_helper=None)
        except Exception as e:
            with excutils.save_and_reraise_exception() as ctxt:
                if not check_error:
                    ctxt.reraise = False


    def db_get_val(self, table, record, column, check_error=False):
        output = self.run_vsctl(["get", table, record, column], check_error)
        if output: 
            return output.rstrip("\n\r")


    def get_port_ofport(self, port_name):
        ofport = self.db_get_val("Interface", port_name, "ofport")
        # This can return a non-integer string, like '[]' so ensure a
        # common failure case
        try:
            int(ofport)
            return ofport
        except (ValueError, TypeError):
            return

