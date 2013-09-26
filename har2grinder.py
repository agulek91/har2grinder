#!/usr/bin/python
import getopt
import sys
import json
from urlparse import urlparse

# Load settings from settings.py
try:
    import settings
except ImportError, e:
    sys.stderr.write("No settings.py file found, will use default values.\n")


def usage():
    print "Usage: " + __file__ + """ har_file
Please provide a HAR file generated by Chrome Dev Tools.
"""
    sys.exit(2)


def main():
    try:
        (opts, args) = getopt.getopt(sys.argv[1:], '')
    except getopt.GetoptError:
        # Print help information and exit:
        usage()
    
    # Check expected number of arguments (at least one filename)
    if len(args) != 1:
        usage()
        
    # Set default option values if not defined in settings.py
    EXCLUDED_DOMAINS = getattr(settings, 'EXCLUDED_DOMAINS', ())
    SLEEP_BETWEEN_PAGES = getattr(settings, 'SLEEP_BETWEEN_PAGES', 3000)

    # Load HAR input file
    input_file_name = args[0]
    try:
        input_file = open(input_file_name, 'r')
        input_json = input_file.read()
    except IOError:
        print 'Error: could not open ' + input_file_name + ' for reading. Exiting.'
        sys.exit(2)

    # Parse HAR input JSON
    try:
        har_data = json.loads(input_json)
    except Exception:
        print 'Error: could parse HAR file ' + input_file_name + '. Exiting.'
        sys.exit(2)

    page_by_id = {}
    requests_section = ''
    headers_section = ''
    page_section = ''
    call_section = ''
    instruments_section = ''

    # Process data from loaded HAR file
    page_number = 0
    for page in har_data.get('log').get('pages'):
        page_number += 1
        page['grinder'] = {}
        page['grinder']['entries'] = []

        page['grinder']['test_number'] = page_number * 1000
        page['grinder']['highest_test_number'] = page['grinder']['test_number']
        page['grinder']['function_code'] = ''
        page_by_id[page.get('id')] = page

    for entry in har_data.get('log').get('entries'):
        request = entry.get('request')
        url = request.get('url')
        url_parsed = urlparse(url)
        if url_parsed.netloc in EXCLUDED_DOMAINS:
            continue

        page_id = entry.get('pageref')
        page = page_by_id[page_id]
        page['grinder']['highest_test_number'] += 1
        test_number = page['grinder']['highest_test_number']

        # entry['grinder'] = {}
        # entry['grinder']['test_number'] = test_number

        headers = request.get('headers')
        method = request.get('method')
        path = url_parsed.path
        grinder_url = "%s://%s" % (url_parsed.scheme, url_parsed.netloc)
        grinder_path = url[len(grinder_url)+1:]

        requests_section += "request%i = createRequest(Test(%i, '%s %s'), '%s', headers%i)\n" % \
                            (test_number, test_number, method, path, grinder_url, test_number)

        entry_headers = ''
        for header in headers:
            entry_headers += "  NVPair('%s', '%s'),\n" % (header.get('name'), header.get('value'))
        entry_headers = "headers%i = [%s]\n" % (test_number, entry_headers)
        headers_section += entry_headers

        page['grinder']['function_code'] += "        request%i.%s('%s')\n" % (test_number, method, grinder_path)

    page_number = 0
    for page in har_data.get('log').get('pages'):
        page_number += 1

        test_number = page.get('grinder').get('test_number')
        function_code = page.get('grinder').get('function_code')[8:]
        page_section += "    def page%i(self):\n        result = %s\n        return result\n\n" \
                        % (page_number, function_code)

        if page_number == 1:
            call_section += '        self.page%i()\n' % (page_number, )
        else:
            call_section += '        grinder.sleep(%i)\n        self.page%i()\n' % (SLEEP_BETWEEN_PAGES, page_number)

        instruments_section += "Test(%i, '%s').record(TestRunner.page%i)\n" \
                               % (test_number, page.get('id'), page_number)

    output = """
# The Grinder 3.11
# HTTP script recorded by har2grinder

from net.grinder.script import Test
from net.grinder.script.Grinder import grinder
from net.grinder.plugin.http import HTTPPluginControl, HTTPRequest
from HTTPClient import NVPair
connectionDefaults = HTTPPluginControl.getConnectionDefaults()
httpUtilities = HTTPPluginControl.getHTTPUtilities()

# To use a proxy server, uncomment the next line and set the host and port.
# connectionDefaults.setProxyServer("localhost", 8001)

def createRequest(test, url, headers=None):
    request = HTTPRequest(url=url)
    if headers: request.headers=headers
    test.record(request, HTTPRequest.getHttpMethodFilter())
    return request

# These definitions at the top level of the file are evaluated once,
# when the worker process is started.

connectionDefaults.defaultHeaders = []

#HEADERS SECTION
%s

# REQUESTS SECTION
%s

class TestRunner:
    \"\"\"A TestRunner instance is created for each worker thread.\"\"\"
%s

    def __call__(self):
        \"\"\"Called for every run performed by the worker thread.\"\"\"
%s

# Instrument page methods.
%s
""" % (headers_section, requests_section, page_section, call_section, instruments_section)

    print output


if __name__ == "__main__":
    main()
