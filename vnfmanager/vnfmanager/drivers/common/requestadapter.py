import json
import requests
import logging.config
import subprocess
import tempfile

class HTTPClient(object):

    def __init__(self,ip,port):
 
        self.ip=ip
        self.port=port
        self.url="http://"+str(self.ip)+":"+str(port)
        self.headers = {'content-type': 'application/json',
                   'Accept': 'application/json'}

    def do_request(self,
                   requests_method,
                   uri,
                   params=None,
                   data=None,
                   expected_status_code=200,
                   method=None):
        body = json.dumps(data) if data is not None else None
        
        headers=self.headers
        request_url = '{0}{1}'.format(self.url, uri)
        response=requests_method(request_url,
                                 params=params,
                                 data=body,
                                 headers=headers)
        try:
            return response.json()
        except:
            return response 

    def get(self,uri,params=None,expected_status_code=200):
        return self.do_request(requests.get,
                               uri,
                               params=params,
                               expected_status_code=expected_status_code)

    def post(self, uri, data=None, params=None,
             expected_status_code=200):
        return self.do_request(requests.post,
                               uri,
                               data=data,
                               params=params,
                               expected_status_code=expected_status_code)



    def put(self, uri, data=None, params=None, expected_status_code=200):
        return self.do_request(requests.put,
                               uri,
                               data=data,
                               params=params,
                               expected_status_code=expected_status_code)

    def delete(self,uri, data=None, params=None, expected_status_code=200):
        return self.do_request(requests.delete,
                               uri,
                               data=data,
                               params=params,
                               expected_status_code=expected_status_code) 
