import requests

proxies = {

      "no_proxy": "192.168.253.6,192.168.1.3,192.168.253.153",
   }
headers_final = {"Accept":"application/json","content-length":0}

class ApiAdapter(object):

    def __init__(self, **kwargs):
        self.verify=kwargs['verify']
        self.auth=kwargs['auth']
        self.headers=kwargs['headers']

    def post(self,path_uri,data=None):
        response = requests.post(path_uri, data=data, verify=self.verify, auth=self.auth, headers=self.headers,proxies=proxies)
        return response

    def get(self,path_uri):
        response = requests.get(path_uri, verify=self.verify, auth=self.auth, headers=self.headers,proxies=proxies)
        return response

    def delete(self,path_uri):
        response = requests.delete(path_uri, verify=self.verify, auth=self.auth, headers=self.headers,proxies=proxies)
        return response

    def put(self,path_uri, data=None):
        response = requests.put(path_uri, data=data, verify=self.verify, auth=self.auth, headers=self.headers,proxies=proxies)
        return response
