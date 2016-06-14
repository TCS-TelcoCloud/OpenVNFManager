import time
from common.apiadapter import ApiAdapter
from vnfmanager.common.requestadapter import  HTTPClient
import paramiko
import json
import logging.config
logger = logging.getLogger(__name__)

class Router():
    def __init__(self, **kwargs): ##extract hostname i.e mgmt ip
        self.host = None
        self.username = kwargs['username']
        self.password = kwargs['password']
        self.verify = False
        self.auth = (self.username,self.password)
        self.headers = {"Accept":"application/json","content-length":0}
        self.masklen = "24"
        self.api = ApiAdapter(verify = self.verify, auth=self.auth, headers = self.headers)

    def config(self, **kwargs):
        time.sleep(10)
        status = ''
        self.host = kwargs['mgmt-ip']
        self.pubIF = kwargs['conf']['pubIF']
        self.testIF1 = kwargs['conf']['testIF1']
        self.testIF2 = kwargs['conf']['testIF2']
        logger.debug("**********************************OUTPUT*********************************************************")
        logger.debug(self.host)
        logger.debug(self.pubIF)
        
        uri = "https://"+self.host
        try:
            self._set_ext_interface()

            session_uri = uri+"/rest/conf"
            session_response = self.api.post(session_uri)
            self.session_id = session_response.headers["location"]

            nat_outbound_uri = uri+"/"+self.session_id+"/set/service/nat/source/rule/10/outbound-interface/"+self.public_interface
            nat_outbound_response = self.api.put(nat_outbound_uri)
            logger.debug(nat_outbound_response.__dict__)
            nat_source_uri = uri+"/"+self.session_id+"/set/service/nat/source/rule/10/source/address/"+self._get_subnet_range(self.testIF1)
            nat_source_response = self.api.put(nat_source_uri)
            logger.debug(nat_source_response.__dict__)
            nat_translation_uri = uri+"/"+self.session_id+"/set/service/nat/source/rule/10/translation/address/"+self.pubIF
            nat_translation_response = self.api.put(nat_translation_uri)
            logger.debug(nat_translation_response.__dict__)

            nat_outbound_uri2 = uri+"/"+self.session_id+"/set/service/nat/source/rule/11/outbound-interface/"+self.public_interface
            nat_outbound_response2 = self.api.put(nat_outbound_uri2)
            logger.debug(nat_outbound_response2.__dict__)
            nat_source_uri2 = uri+"/"+self.session_id+"/set/service/nat/source/rule/11/source/address/"+self._get_subnet_range(self.testIF2)
            nat_source_response2 = self.api.put(nat_source_uri2)
            logger.debug(nat_source_response2.__dict__)
            nat_translation_uri2 = uri+"/"+self.session_id+"/set/service/nat/source/rule/11/translation/address/"+self.pubIF
            nat_translation_response2 = self.api.put(nat_translation_uri2)
            logger.debug(nat_translation_response2.__dict__)
            
            nat_destination_uri = uri+"/"+self.session_id+"/set/service/nat/destination/rule/9/destination/address/"+self.pubIF
            nat_destination_response = self.api.put(nat_destination_uri)
            logger.debug(nat_destination_response.__dict__)
            nat_inbound_uri = uri+"/"+self.session_id+"/set/service/nat/destination/rule/9/inbound-interface/"+self.public_interface
            nat_inbound_response = self.api.put(nat_inbound_uri)
            logger.debug(nat_inbound_response.__dict__)
            nat_translation_dest_uri = uri+"/"+self.session_id+"/set/service/nat/destination/rule/9/translation/address/"+self._get_subnet_range(self.pubIF)
            nat_translation_dest_response = self.api.put(nat_translation_dest_uri)
            logger.debug(nat_translation_dest_response.__dict__)

            nat_destination_uri1 = uri+"/"+self.session_id+"/set/service/nat/destination/rule/10/destination/address/"+self.pubIF
            nat_destination_response1 = self.api.put(nat_destination_uri1)
            logger.debug(nat_destination_response1.__dict__)
            nat_inbound_uri1 = uri+"/"+self.session_id+"/set/service/nat/destination/rule/10/inbound-interface/"+self.public_interface
            nat_inbound_response1 = self.api.put(nat_inbound_uri1)
            logger.debug(nat_inbound_response1.__dict__)
            nat_translation_dest_uri1 = uri+"/"+self.session_id+"/set/service/nat/destination/rule/10/translation/address/"+self._get_subnet_range(self.testIF1)
            nat_translation_dest_response1 = self.api.put(nat_translation_dest_uri1)
            logger.debug(nat_translation_dest_response1.__dict__)
            
            nat_destination_uri2 = uri+"/"+self.session_id+"/set/service/nat/destination/rule/11/destination/address/"+self.pubIF
            nat_destination_response2 = self.api.put(nat_destination_uri2)
            logger.debug(nat_destination_response2.__dict__)
            nat_inbound_uri2 = uri+"/"+self.session_id+"/set/service/nat/destination/rule/11/inbound-interface/"+self.public_interface
            nat_inbound_response2 = self.api.put(nat_inbound_uri2)
            logger.debug(nat_inbound_response2.__dict__)
            nat_translation_dest_uri2 = uri+"/"+self.session_id+"/set/service/nat/destination/rule/11/translation/address/"+self._get_subnet_range(self.testIF2)
            nat_translation_dest_response2 = self.api.put(nat_translation_dest_uri2)
            logger.debug(nat_translation_dest_response2.__dict__)
            
            protocols_uri = uri+"/"+self.session_id+"/set/protocols/static/route/0.0.0.0%2F0/next-hop/"+self._get_gateway(self.pubIF)
            protocols_response = self.api.put(protocols_uri)
            logger.debug(protocols_response.__dict__)

            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            ssh.connect(self.host, username='root',password='vyatta')
            stdin, stdout, stderr =  ssh.exec_command("sudo ip r del default")
            logger.debug(stdout.readlines())
            logger.debug(stderr.readlines())
             
            commit_uri = uri+"/"+self.session_id+"/commit"
            commit_response = self.api.post(commit_uri)
            logger.debug(commit_response.__dict__)
            save_uri = uri+"/"+self.session_id+"/save"
            save_response = self.api.post(save_uri)
            logger.debug(save_response.__dict__)

            status = "COMPLETE"
        except Exception as e:
            logger.debug(e)
            logger.debug(e.__str__())
            status = "ERROR"
        return status

    def _get_gateway(self,public_ip):
        ip=public_ip.split(".")
        logger.debug(ip)
        ip.pop()
        logger.debug(ip)
        ip.append('1')
        ip1='.'.join(ip)
        logger.debug(ip1)
        return ip1

    def _get_subnet(self, ip_addr):
        ip=ip_addr.split(".")
        ip.pop()
        ip.append('0')
        return '.'.join(ip)+"/"+ self.masklen

    def _get_subnet_range(self,ip_addr):
        ip=ip_addr.split(".")
        ip.pop()
        ip.append('0')
        #ip_last=ip[:]
        #ip_last[3]='255'
	#ip_range='.'.join(ip)+"-"+'.'.join(ip_last)
        ip_range = '.'.join(ip)+"%2F"+self.masklen
        return ip_range
        
    def _set_ext_interface(self):
        op_uri = "https://"+self.host+"/rest/op/show/interfaces"
        logger.debug(op_uri)
        op_uri_response = self.api.post(op_uri)
        logger.debug(op_uri_response)
        show_interfaces_uri = "https://"+self.host+"/"+op_uri_response.headers["location"]
        show_interfaces_response = self.api.get(show_interfaces_uri)
        for i in range(10):
            if show_interfaces_response.status_code==202:
                show_interfaces_response = self.api.get(show_interfaces_uri)
        interface_list = show_interfaces_response._content.split()
        pub_ip = self.pubIF+"/24"
        for i in range(len(interface_list)):
            if interface_list[i] == pub_ip:
                self.public_interface = interface_list[i-1]
                return
    
    def init(self, **kwargs):
        time.sleep(10)
        self.host = kwargs['mgmt-ip']
        logger.debug("**********************************OUTPUT*********************************************************")
        logger.debug(kwargs)
        return self.execute_ip_set(self.host)

    def execute_ip_set(self, host):
        uri = "https://"+host 
        status = ''
        try:
            session_uri = uri+"/rest/conf"
            session_response = self.api.post(session_uri)
            logger.debug("**********************************OUTPUT*********************************************************")
            logger.debug(session_response)
            self.session_id = session_response.headers["location"]
            show_interfaces_uri = uri+"/"+self.session_id+"/interfaces/dataplane"
            set_interfaces_uri = uri+"/"+self.session_id+"/set/interfaces/dataplane"
            interfaces = self.api.get(show_interfaces_uri)
            logger.debug(interfaces)
            enum = json.loads(interfaces._content)["enum"] 
            children = json.loads(interfaces._content)["children"]
            set_interfaces = []
            for child in children:
                set_interfaces.append(child["name"])
            for i in enum:
                if i not in set_interfaces:
                    set_interface_uri = set_interfaces_uri+"/"+i+"/address/dhcp"
                    response = self.api.put(set_interface_uri)
                    logger.debug(response)
            commit_uri = uri+"/"+self.session_id+"/commit"
            commit_response = self.api.post(commit_uri)
            save_uri = uri+"/"+self.session_id+"/save"
            save_response = self.api.post(save_uri)
            status = 'COMPLETE'
        except Exception as e:
            logger.debug(e.__str__())

            #print e.__str__()
            status = "ERROR"
        finally:
            return status
