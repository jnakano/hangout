import urllib
import hashlib
import cgi
#using these for parsing signed requests
import base64
import hmac
from google.appengine.api import urlfetch
import json

class FacebookError(Exception):
	"""Exception class for errors received from Facebook."""

	def __init__(self, code, msg, args = None):
		self.code = code
		self.msg = msg
		self.args = args

	def __str__(self):
		return 'Error %s: %s' % (self.code, self.msg)

def base64_url_decode(inp):
	padding_factor = (4 - len(inp) % 4) % 4
	inp += "="*padding_factor
	return base64.b64decode(unicode(inp).translate(dict(zip(map(ord, u'-_'), u'+/'))))

class Facebook(object):
		"""
    	Provides access to the Facebook API.

    """
		def __init__(self, secret_key, app_id, canvas_name = None):
			"""
				Initializes a new Facebook object which provides wrappers for the Facebook API.

			"""
			self.canvas_name = canvas_name
			self.app_id = app_id
			self.secret_key = secret_key
			self.access_token = None
			self.me = None
			self.uid = None

		def get_add_url(self):
			return "https://www.facebook.com/dialog/oauth?client_id=" + self.app_id + "&redirect_uri=http://apps.facebook.com/" + self.canvas_name + "/"

		def fql_multiquery(self, queries):
			params = {
			          "queries":json.dumps(queries),
			          "access_token":self.access_token,
			          "format":"json"
			          }

			url = "https://api.facebook.com/method/fql.multiquery?" + urllib.urlencode(params)
			response = urlfetch.fetch(url)

			fql_result_set = json.loads(response.content)
			sorted_results = {}
			for result in fql_result_set:
				sorted_results[result["name"]] = result[u'fql_result_set'][0]

			return sorted_results

		def fql_query(self, query):
			params = {
								"queries":json.dumps(query),
								"access_token":self.access_token,
								"format":"json"
								}

			url = "https://api.facebook.com/method/fql.query?" + urllib.urlencode(params)
			response = urlfetch.fetch(url)
			return json.loads(response.content)

		def urlsafe_b64decode(self, str):
			"""Perform Base 64 decoding for strings with missing padding."""

			l = len(str)
			pl = l % 4
			return base64.urlsafe_b64decode(str.ljust(l + pl, "="))

		def parse_signed_request(self, signed_request):
			"""
			Parse signed_request given by Facebook (usually via POST),
			decrypt with app secret.

			Arguments:
			signed_request -- Facebook's signed request given through POST
			secret -- Application's app_secret required to decrpyt signed_request
			"""

			if "." in signed_request:
				esig, payload = signed_request.split(".")
			else:
				return {}

			sig = self.urlsafe_b64decode(str(esig))
			data = json.loads(self.urlsafe_b64decode(str(payload)))

			if not isinstance(data, dict):
				raise FacebookError("Pyload is not a json string!")
				return {}

			if data["algorithm"].upper() == "HMAC-SHA256":
				if hmac.new(self.secret_key, payload, hashlib.sha256).digest() == sig:
					return data

			else:
				raise FacebookError("Not HMAC-SHA256 encrypted!")

			return {}

		def get_user_access(self, data):
			self.uid = data.get(u'user_id')
			self.access_token = data.get(u'oauth_token')

		def check_authentication(self, request):
			signed_request = request.get("signed_request")
			if signed_request:
				data = self.parse_signed_request(signed_request)
				if data:
					self.get_user_access(data)
				else:
					return False
			else:
				# try cookie
				self.get_user_from_cookie(request.cookies)
			if not self.uid:
				return False
			return True

		def get_args_for_token(self, code, redirect_uri = None):
			args = {
							'code':code,
							'client_id':self.app_id,
							'client_secret':self.secret_key,
							'redirect_uri':redirect_uri
						}
			return args

		def exchange_code_for_auth_token(self, request):
			file = urllib.urlopen("https://graph.facebook.com/oauth/access_token?" + \
			 urllib.urlencode(self.get_args_for_token(request.get('code'), request.application_url + '/')))
			try:
				token_response = file.read()
			finally:
				file.close()

			token_args = cgi.parse_qs(token_response)
			self.access_token = token_args.get('access_token')
			if not self.access_token:
				return None
			me_file = urllib.urlopen("https://graph.facebook.com/me?" + urllib.urlencode({
				'access_token':self.access_token[0]
			}))

			try:
				me_response = me_file.read()
				self.me = json.loads(me_response)
				self.uid = self.me['id']
			finally:
				me_file.close()

			return True


		def get_me(self):
			""" returns the 'me' dict if available """
			return self.me




		def get_user_from_cookie(self, cookies):
			"""Parses the cookie set by the official Facebook JavaScript SDK.

				cookies should be a dictionary-like object mapping cookie names to
				cookie values.

				If the user is logged in via Facebook, we return a dictionary with the
				keys "uid" and "access_token". The former is the user's Facebook ID,
				and the latter can be used to make authenticated requests to the Graph API.
				If the user is not logged in, we return None.

				Download the official Facebook JavaScript SDK at
				http://github.com/facebook/connect-js/. Read more about Facebook
				authentication at http://developers.facebook.com/docs/authentication/.
			"""

			cookie = cookies.get("fbsr_" + self.app_id, "")
			if not cookie:
				return None

			response = self.parse_signed_request(cookie)
			if not response:
				return None



			file = urllib.urlopen("https://graph.facebook.com/oauth/access_token?" + urllib.urlencode(self.get_args_for_token(response['code'])))
			try:
				token_response = file.read()
			finally:
				file.close()

			token_args = cgi.parse_qs(token_response)
			access_token = token_args.get('access_token')
			if not access_token:
				return None
			self.access_token = access_token[-1]
			self.uid = response['user_id']