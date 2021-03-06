# Copyright 2012-2014 Amazon.com, Inc. or its affiliates. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License"). You
# may not use this file except in compliance with the License. A copy of
# the License is located at
#
# http://aws.amazon.com/apache2.0/
#
# or in the "license" file accompanying this file. This file is
# distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF
# ANY KIND, either express or implied. See the License for the specific
# language governing permissions and limitations under the License.

import os
import glob
import json
import pprint
import logging
import difflib
from tests import unittest, create_session

from mock import Mock
from botocorev063p.vendored.requests.structures import CaseInsensitiveDict

import botocorev063p.session
from botocorev063p.response import XmlResponse, JSONResponse, get_response
from botocorev063p.exceptions import IncompleteReadError

log = logging.getLogger(__name__)

def check_dicts(xmlfile, d1, d2):
    if d1 != d2:
        log.debug('-' * 40)
        log.debug(xmlfile)
        log.debug('-' * 40)
        log.debug(pprint.pformat(d1))
        log.debug('-' * 40)
        log.debug(pprint.pformat(d2))
    if not d1 == d2:
        # Borrowed from assertDictEqual, though this doesn't
        # handle the case when unicode literals are used in one
        # dict but not in the other (and we want to consider them
        # as being equal).
        pretty_d1 = pprint.pformat(d1, width=1).splitlines()
        pretty_d2 = pprint.pformat(d2, width=1).splitlines()
        diff = ('\n' + '\n'.join(difflib.ndiff(pretty_d1, pretty_d2)))
        raise AssertionError("Dicts are not equal:\n%s" % diff)


def save_jsonfile(jsonfile, r):
    """
    This is a little convenience when creating new tests.
    You just have to drop the XML file into the data directory
    and then, if not JSON file is present, this code will
    create the JSON file and dump the parsed value into it.
    Of course, you need to validate that the JSON is correct
    but it makes it easy to bootstrap more tests.
    """
    if not os.path.isfile(jsonfile):
        fp = open(jsonfile, 'w')
        json.dump(r.get_value(), fp, indent=4)
        fp.close()


def test_xml_parsing():
    for dp in ['responses', 'errors']:
        data_path = os.path.join(os.path.dirname(__file__), 'xml')
        data_path = os.path.join(data_path, dp)
        session = create_session()
        xml_files = glob.glob('%s/*.xml' % data_path)
        service_names = set()
        for fn in xml_files:
            service_names.add(os.path.split(fn)[1].split('-')[0])
        for service_name in service_names:
            service = session.get_service(service_name)
            service_xml_files = glob.glob('%s/%s-*.xml' % (data_path,
                                                           service_name))
            for xmlfile in service_xml_files:
                dirname, filename = os.path.split(xmlfile)
                basename = os.path.splitext(filename)[0]
                jsonfile = os.path.join(dirname, basename + '.json')
                sn, opname = basename.split('-', 1)
                opname = opname.split('#')[0]
                operation = service.get_operation(opname)
                r = XmlResponse(session, operation)
                fp = open(xmlfile)
                xml = fp.read()
                fp.close()
                r.parse(xml, 'utf-8')
                save_jsonfile(jsonfile, r)
                fp = open(jsonfile)
                data = json.load(fp)
                fp.close()
                yield check_dicts, xmlfile, r.get_value(), data


def test_json_parsing():
    input_path = os.path.join(os.path.dirname(__file__), 'json')
    input_path = os.path.join(input_path, 'inputs')
    output_path = os.path.join(os.path.dirname(__file__), 'json')
    output_path = os.path.join(output_path, 'outputs')
    session = botocorev063p.session.get_session()
    jsonfiles = glob.glob('%s/*.json' % input_path)
    service_names = set()
    for fn in jsonfiles:
        service_names.add(os.path.split(fn)[1].split('-')[0])
    for service_name in service_names:
        service = session.get_service(service_name)
        service_input_files = glob.glob('%s/%s-*.json' % (input_path,
                                                          service_name))
        for inputfile in service_input_files:
            dirname, filename = os.path.split(inputfile)
            outputfile = os.path.join(output_path, filename)
            basename = os.path.splitext(filename)[0]
            sn, opname = basename.split('-', 1)
            operation = service.get_operation(opname)
            r = JSONResponse(session, operation)
            headers = {}
            with open(inputfile, 'r') as fp:
                jsondoc = fp.read()
                # Try to get any headers using a special key
                try:
                    parsed = json.loads(jsondoc)
                except ValueError:
                    # This will error later, let it go on
                    parsed = {}
                if '__headers' in parsed:
                    headers = parsed['__headers']
                    del parsed['__headers']
                    jsondoc = json.dumps(parsed)
            r.parse(jsondoc.encode('utf-8'), 'utf-8')
            r.merge_header_values(headers)
            save_jsonfile(outputfile, r)
            fp = open(outputfile)
            data = json.load(fp)
            fp.close()
            yield check_dicts, inputfile, r.get_value(), data


class TestHeaderParsing(unittest.TestCase):

    maxDiff = None

    def setUp(self):
        self.session = botocorev063p.session.get_session()
        self.s3 = self.session.get_service('s3')

    def test_put_object(self):
        http_response = Mock()
        http_response.encoding = 'utf-8'
        http_response.headers = CaseInsensitiveDict(
            {'Date': 'Thu, 22 Aug 2013 02:11:57 GMT',
             'Content-Length': '0',
             'x-amz-request-id': '2B74ECB010FF029E',
             'ETag': '"b081e66e7e0c314285c655cafb4d1e71"',
             'x-amz-id-2': 'bKECRRBFttBRVbJPIVBLQwwipI0i+s9HMvNFdttR17ouR0pvQSKEJUR+1c6cW1nQ',
             'Server': 'AmazonS3',
             'content-type': 'text/xml'})
        http_response.content = ''
        put_object = self.s3.get_operation('PutObject')
        expected = {"ETag": '"b081e66e7e0c314285c655cafb4d1e71"'}
        response_data = get_response(self.session, put_object, http_response)[1]
        self.assertEqual(response_data, expected)

    def test_head_object(self):
        http_response = Mock()
        http_response.encoding = 'utf-8'
        http_response.headers = CaseInsensitiveDict(
            {'Date': 'Thu, 22 Aug 2013 02:11:57 GMT',
             'Content-Length': '265',
             'x-amz-request-id': '2B74ECB010FF029E',
             'ETag': '"40d06eb6194712ac1c915783004ef730"',
             'Server': 'AmazonS3',
             'content-type': 'binary/octet-stream',
             'Content-Type': 'binary/octet-stream',
             'accept-ranges': 'bytes',
             'Last-Modified': 'Tue, 20 Aug 2013 18:33:25 GMT',
             'x-amz-server-side-encryption': 'AES256',
             'x-amz-meta-mykey1': 'value1',
             'x-amz-meta-mykey2': 'value2',
             })
        http_response.content = ''
        http_response.request.method = 'HEAD'
        put_object = self.s3.get_operation('HeadObject')
        expected = {"AcceptRanges": "bytes",
                    "ContentType": "binary/octet-stream",
                    "LastModified": "Tue, 20 Aug 2013 18:33:25 GMT",
                    "ContentLength": "265",
                    "ETag": '"40d06eb6194712ac1c915783004ef730"',
                    "ServerSideEncryption": "AES256",
                    "Metadata": {
                        'mykey1': 'value1',
                        'mykey2': 'value2',
                    }}
        response_data = get_response(self.session, put_object,
                                     http_response)[1]
        self.assertEqual(response_data, expected)

    def test_list_objects_with_invalid_content_length(self):
        http_response = Mock()
        http_response.encoding = 'utf-8'
        http_response.headers = CaseInsensitiveDict(
            {'Date': 'Thu, 22 Aug 2013 02:11:57 GMT',
             # We say we have 265 bytes but we're returning 0,
             # this should raise an exception because this is not
             # a HEAD request.
             'Content-Length': '265',
             'x-amz-request-id': '2B74ECB010FF029E',
             'ETag': '"40d06eb6194712ac1c915783004ef730"',
             'Server': 'AmazonS3',
             'content-type': 'binary/octet-stream',
             'Content-Type': 'binary/octet-stream',
             'accept-ranges': 'bytes',
             'Last-Modified': 'Tue, 20 Aug 2013 18:33:25 GMT',
             'x-amz-server-side-encryption': 'AES256'
             })
        http_response.content = ''
        http_response.request.method = 'GET'
        list_objects = self.s3.get_operation('ListObjects')
        expected = {"AcceptRanges": "bytes",
                    "ContentType": "binary/octet-stream",
                    "LastModified": "Tue, 20 Aug 2013 18:33:25 GMT",
                    "ContentLength": "265",
                    "ETag": '"40d06eb6194712ac1c915783004ef730"',
                    "ServerSideEncryption": "AES256"
                    }
        with self.assertRaises(IncompleteReadError):
            response_data = get_response(self.session, list_objects,
                                         http_response)[1]

    def test_head_object_with_json(self):
        http_response = Mock()
        http_response.encoding = 'utf-8'
        http_response.headers = CaseInsensitiveDict(
            {'Date': 'Thu, 22 Aug 2013 02:11:57 GMT',
             'Content-Length': '0',
             'x-amz-request-id': '2B74ECB010FF029E',
             'ETag': '"40d06eb6194712ac1c915783004ef730"',
             'Server': 'AmazonS3',
             'content-type': 'application/json',
             'Content-Type': 'application/json',
             'accept-ranges': 'bytes',
             'Last-Modified': 'Tue, 20 Aug 2013 18:33:25 GMT',
             'x-amz-server-side-encryption': 'AES256'})
        http_response.content = ''
        put_object = self.s3.get_operation('HeadObject')
        expected = {"AcceptRanges": "bytes",
                    "ContentType": "application/json",
                    "LastModified": "Tue, 20 Aug 2013 18:33:25 GMT",
                    "ContentLength": "0",
                    "ETag": '"40d06eb6194712ac1c915783004ef730"',
                    "ServerSideEncryption": "AES256"
                    }
        response_data = get_response(self.session, put_object,
                                     http_response)[1]
        self.assertEqual(response_data, expected)
