import uuid
from vnfsvc.client import client

class VNFDParserUtils(object):

    def __init__(self, vnf_context, nsd, vnfd_name):
        self.neutronclient = client.NeutronClient(vnf_context)
        self.nsd = nsd
        self.vnfd_name = vnfd_name

    def template(self, data, new_vnfd, vnfd):
        for key in data['vnfd']:
            method_key = vnfd.available_keys[key].replace('-','_')
            getattr(self, method_key)(data['vnfd'][key], new_vnfd)

    def vdus(self, data, new_vnfd, vnfd):
        self.template(vnfd.vnfd['template'], new_vnfd, vnfd)
        for vdu in data.keys():
            if vdu not in vnfd.vdu_list:
                continue
            for key in data[vdu]:
                if key != 'vdu-id':
                    method_key = vnfd.available_keys[key].replace('-','_')
                    getattr(self, method_key)(data[vdu][key], vdu, new_vnfd)

    def num_instances(self, data, vdu, new_vnfd):
        new_vnfd['vdus'][vdu]['vm_details']['num-instances'] = data

    def lifecycle_event(self, data, vdu, new_vnfd):
        new_vnfd['vdus'][vdu]['postconfigure']['lifecycle_events'] = data

    def diagnostics_params(self, data, vdu, new_vnfd):
        new_vnfd['vdus'][vdu]['postconfigure']['diagnostics_params'] = data

    def vm_details(self, data, vdu, new_vnfd):
        new_vnfd['vdus'][vdu]['vm_details']['image_details'] = data

    def disk(self, data, vdu, new_vnfd):
        new_vnfd['vdus'][vdu]['vm_details']['disk'] = data

    def vcpus(self, data, vdu, new_vnfd):
        new_vnfd['vdus'][vdu]['vm_details']['vcpus'] = data['num-vcpu']

    def memory(self, data, vdu, new_vnfd):
        new_vnfd['vdus'][vdu]['vm_details']['ram'] = data['total-memory-mb']

    def other_constraints(self, data, vdu, new_vnfd):
        if data:
            new_vnfd['vdus'][vdu]['preconfigure']['other_constraints'] = data

    def network_interfaces(self, data, vdu, new_vnfd):
        new_vnfd['vdus'][vdu]['vm_details']['network_interfaces'] = data
        ni = new_vnfd['vdus'][vdu]['vm_details']['network_interfaces']
        for key in data:
            ref = ni[key]['connection-point-ref'].split('/')[1]
            ni[key].update(self.nsd['vdus'][self.vnfd_name+':'+vdu]['networks'][ref])
            if 'fixed-ip' in new_vnfd['connection_point'][ref].keys():
                fixed_ip = new_vnfd['connection_point'][ref]['fixed-ip']
                subnet_id = ni[key]['subnet-id']
                net_id = ni[key]['net-id']
                if fixed_ip == 'gateway':
                    subnet = self.neutronclient.show_subnet(subnet_id)
                    port_ip = subnet['subnet']['gateway_ip']
                else:
                    port_ip = fixed_ip

                port_dict = {'port':{}}
                port_dict['port']['network_id'] = net_id
                port_dict['port']['fixed_ips'] = [{
                    'subnet_id': subnet_id,
                    'ip_address': port_ip,
                }]
                port_dict['port']['admin_state_up'] = True
                port = self.neutronclient.create_port(port_dict)
                ni[key]['port_id'] = port['port']['id']
            if 'properties' in ni[key].keys():
                new_vnfd['vdus'][vdu]['mgmt-driver'] = ni[key]['properties']['driver']

    def assurance_params(self, data, new_vnfd, vnfd):
         new_vnfd['postconfigure']['assurance_params'] = data

    def implementation_artifact(self, data, vdu, new_vnfd):
        artifact_dict = dict()
        new_vnfd['vdus'][vdu]['vm_details']['userdata'] = data['deployment_artifact']
        artifact_dict['cfg_engine'] = data.get('cfg_engine', None)
        artifact_dict['deployment_artifact'] = data['deployment_artifact']
        if 'implementation_artifact' in new_vnfd['vdus'][vdu]['preconfigure'].keys():
            new_vnfd['vdus'][vdu]['preconfigure']['implementation_artifact'].append(artifact_dict)
        else:
            new_vnfd['vdus'][vdu]['preconfigure']['implementation_artifact'] = [artifact_dict]

    def connection_point(self, data, new_vnfd):
        new_vnfd['connection_point'] = data


    def get_flavor_dict(self, vdu):
        flavor_dict = dict()
        flavor_dict['ram'] = vdu['vm_details']['ram']
        flavor_dict['vcpus'] = vdu['vm_details']['vcpus']
        flavor_dict['disk'] = vdu['vm_details']['disk']
        flavor_dict['name'] = str(uuid.uuid4()).split('-')[0]
        return flavor_dict

    def get_boot_details(self, vdu):
        """ Returns the dictionary that contains all necessary information to launch a VM """
        boot_dict = dict()
        boot_dict['image'] = vdu['vm_details']['image_details']
        boot_dict['num_instances'] = vdu['vm_details']['num-instances']
        if 'userdata' in vdu['vm_details'].keys():
            boot_dict['userdata'] = vdu['vm_details']['userdata']
        return boot_dict

