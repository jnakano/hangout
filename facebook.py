import time
import urllib
import hashlib
import cgi
#using these for parsing signed requests
import base64
import hmac
from google.appengine.api import urlfetch
from google.appengine.ext import webapp
from model.conf import Conf
FACEBOOK_URL = 'http://api.facebook.com/'

class FacebookError(Exception):
    """Exception class for errors received from Facebook."""

    def __init__(self, code, msg, args=None):
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

    def __init__(self, secret_key, app_id, canvas_name):
        """
        Initializes a new Facebook object which provides wrappers for the Facebook API.

        """
        self.canvas_name = canvas_name
        self.app_id = app_id
        self.secret_key = secret_key
        self.access_token = None
        self.uid = None

    def get_add_url(self):
        return "https://www.facebook.com/dialog/oauth?client_id=" + self.app_id + "&redirect_uri=http://apps.facebook.com/"+self.canvas_name+"/"

    def fql_multiquery(self,queries):
        """
        
        """
        params = {
                  "queries":simplejson.dumps(queries),
                  "access_token":self.access_token,
                  "format":"json"
                  }
        
        url = "https://api.facebook.com/method/fql.multiquery?" + urllib.urlencode(params)
        response = urlfetch.fetch(url)
        return simplejson.loads(response.content)

    def fql_query(self,query):
        params = {
                  "queries":simplejson.dumps(query),
                  "access_token":self.access_token,
                  "format":"json"
                  }
        
        url = "https://api.facebook.com/method/fql.query?" + urllib.urlencode(params)
        response = urlfetch.fetch(url)
        return simplejson.loads(response.content)

    def parse_signed_request(self,signed_request):
      l = signed_request.split('.', 2)
      encoded_sig = l[0]
      payload = l[1]
  
      sig = base64_url_decode(encoded_sig)
      data = simplejson.loads(base64_url_decode(payload))
  
      if data.get('algorithm').upper() != 'HMAC-SHA256':
          return
      
      expected_sig = hmac.new(self.secret_key, msg=payload, digestmod=hashlib.sha256).digest()
      
      if sig == expected_sig and data[u'issued_at'] > (time.time() - 86400):
        return data
      
      return None
      
    def check_credits(self,request,onGetItems,onGetStatus):
      """
        @param onGetItems: 
          A function that accepts the following params:
          
          @param method: The method of the request
          @param payload: The credits data facebook passes back to the app
          
          @return: dict of the results
          
        @param onGetStatus:
          A function that accepts the following params:
          
          @param method: The method of the request
          @param payload: The credits data facebook passes back to the app
          
          @return: dict of the results
      """
      from model import facebook_methods
      from model.models import Item,Component
      import logging
      
      signed_request = request.get('signed_request')
      data = self.parse_signed_request(signed_request)
      if not data:
        return False
      payload = data['credits']
      method = request.get('method')
      if method == facebook_methods.PAYMENTS_GET_ITEMS:
        result = onGetItems(method,payload)
#        result = '{"content":[{"title":"[Test Mode] Unicorn","description":"[Test Mode] Own your own mythical beast!","price":2,"image_url":"http:\/\/www.facebook.com\/images\/gifts\/21.png","product_url":"http:\/\/www.facebook.com\/images\/gifts\/21.png"}],"method":"payments_get_items"}'
      elif method == facebook_methods.PAYMENTS_STATUS_UPDATE:
        result = onGetStatus(method,payload)
      result = simplejson.dumps(result)
      logging.debug('returned to facebook %s ' % result)
      return result
      
        
    def get_user_access(self,data):
      self.uid = data.get(u'user_id')
      self.access_token = data.get(u'oauth_token')
    
    def check_authentication(self,request):
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
    
    def get_user_from_cookie(self,cookies):
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
        cookie = cookies.get("fbs_" + self.app_id, "")
        if not cookie: return
        args = dict((k, v[-1]) for k, v in cgi.parse_qs(cookie.strip('"')).items())
        payload = "".join(k + "=" + args[k] for k in sorted(args.keys())
                          if k != "sig")
        sig = hashlib.md5(payload + self.secret_key).hexdigest()
        expires = int(args["expires"])
        if sig == args.get("sig") and (expires == 0 or time.time() < expires):
            self.uid = args.get("uid")
            self.access_token = args.get("access_token")

config = Conf()          
class FacebookCreditsHandler(webapp.RequestHandler):
  def post(self):
    self.fb = Facebook(config.facebook_app_secret,config.facebook_app_id,config.facebook_canvas_name)
    self.response.headers['Content-Type'] = "application/json"
    self.response.out.write(self.fb.check_credits(self.request, self.onGetItems, self.onGetStatus))
    
  def getTestComponent(self):
    from model.models import Component
    import datetime
    return Component(expires = datetime.datetime.now() + datetime.timedelta(seconds = 12800),hp=100,upCash=100,upSteel=100,buildtime=159000,state=3).put().id()
  
  def onGetItems(self,method,payload):
    """
      Facebook calls this method to get details about an item
    """
    from django.utils import simplejson
    import model
    from math import ceil
    from model.models import Item,Component
    from model import product_types
    from model import resource_types
    from model import component_states
    import datetime
    import logging
    
    result = {'method':method}
    logging.debug('method %s' % method)
    logging.debug(payload['order_info'])
    order_info = simplejson.loads(payload['order_info'])[0]
    logging.debug('order_info %s' % order_info)
    # research component
    # building
    #     we know it's repair if health is < 100%
    #     if it's upgrading if timeLeft = item.buildtime - ( now() - building.created ) <= 0 it has been built
    #     else its constructed
    # unit
    # a component is always only speed up
    # what kind of product is this?
    product_type = order_info['type']
    test = order_info.get('test')
    price = 0
    title = ''
    product_url = self.request.host_url
    image_url = ''
    desc = ''
    product_data = {'type':product_type}
    
    if product_type == product_types.TOKENS:
      from model import math_util
      image_url = self.request.host_url + '/static/tokens.png'
      amount = order_info['amount']
      tokenPacks = [int(s) for s in config.dynamic['tokenPacks'].split(',')]
      if amount not in tokenPacks:
        logging.debug('amount not in tokenPacks')
        return None # can't order less
      
      tokens = amount
      if tokenPacks.index(amount) != 0:
        bonus = config.dynamic['tokenBasePrice'] * amount
        tokens += bonus
      
      title = '%s Air Tokens' % math_util.splitthousands(str(int(tokens)))
      desc = title
      price = int(config.dynamic['tokenBasePrice'] * amount)
      product_data['tokens'] = int(tokens)
      logging.debug('total price of tokens: %s' % price)
    elif product_type == product_types.RESOURCES:
      title = 'Get Resources'
      image_url = self.request.host_url + '/static/resources.png'
      amounts = order_info['resources']
      for type,amt in amounts.iteritems():
        logging.debug('ordered %s of rsrc %s ' % (amt,type))
        if type == resource_types.CASH:
          conversion_rate = config.dynamic['cashCreditRatio']
        elif type == resource_types.FUEL:
          conversion_rate = (amt / config.dynamic['fuelCashRatio']) * config.dynamic['cashCreditRatio']
        elif type == resource_types.STEEL:
          conversion_rate = (amt / config.dynamic['steelCashRatio']) * config.dynamic['cashCreditRatio']
        product_data[type] = amt
        price += int(round(conversion_rate * amt))
      logging.debug('total price of resources: %s' % price)
    elif product_type == product_types.SPEED_UPS:
      c_id = order_info['cId']
      if test:
        logging.debug('is test')
        c_id = self.getTestComponent()
      image_url = self.request.host_url + '/static/speedup.png'
      # get the component Id
      
      logging.debug('cId %s' % c_id)
      component = Component.get_by_id(int(c_id))
      # is the component still constructing?
      is_complete = model.isComponentComplete(component)
      logging.debug('expires %s' % component.expires)
      logging.debug('now %s' % datetime.datetime.now())
      logging.debug('is_complete %s' % is_complete)
      
      if not is_complete:
        time_left = (component.expires - datetime.datetime.now()).seconds * 1000
        logging.debug('time_left %s' % time_left)
        if time_left > config.dynamic['freeSpeedMax']:
          mins_left = time_left/1000/60 # convert milliseconds to minutes
          price = int(ceil(config.dynamic['costPerMinute'] * mins_left))
          
          if component.state == component_states.CONSTRUCT:
            title = 'Finishing Construction'
            desc = "Buy this item"
          elif component.state == component_states.REPAIR:
            title = 'Finish Repair'
            desc = "Buy this item"
          elif component.state == component_states.RESEARCH:
            title = 'Finish Research'
            desc = "Buy this item"
          elif component.state == component_states.UPGRADE:
            title = 'Finish Upgrade'
            desc = "Buy this item"
            
#          price = 5

    product = {
               'item_id':24107,
               'title':title,
               'description':desc,
               'price':int(price * config.dynamic['creditsToDollars']),
               'image_url':image_url,
               'product_url':product_url,
               'data':simplejson.dumps(product_data)
               }
    
    result['content'] = [product]
    return result
    
  def onGetStatus(self,method,payload):
    from django.utils import simplejson
    import logging
    import model
    from model import product_types
    from model.models import Item,Component,ConfigDB
    from model import resource_types
    from model import spreadsheet
    from model import component_states

    status = payload['status']
    order_id = payload['order_id']
    logging.debug('onGetStatus: order_id: %s' % order_id)
    
    result = {'method':method}
    result['content'] = {
                         'status':'settled',
                         'order_id':order_id
                         }
    
    if status == 'placed':
      # just return settled status to Facebook, this may be called twice
      order_details = simplejson.loads(payload['order_details'])
      logging.debug('placed: order_details: %s' % payload['order_details'])
      # check and log here
    elif status == 'settled':
      
      order_details = simplejson.loads(payload['order_details'])
      logging.debug('settled: order_details %s' % payload['order_details'])
      # order_details:{order_id:0,buyer:0,app:0,receiver:0,amount:0,update_time:0,time_placed:0,data:'',items:[{}],status:'placed'}
      buyer = order_details['buyer']
      logging.debug('buyer %s' % buyer)
      order_item = order_details['items'][0]
      data = simplejson.loads(order_item['data'])
      
      logging.debug('data dump: %s' % simplejson.dumps(data))
      logging.debug('order_item dump: %s' % simplejson.dumps(order_item))
      
      type = data['type']
      player = model.getFacebookPlayer(str(buyer))
      
      # must have been resource purchase
      if type == product_types.TOKENS:
        tokens = int(data.get('tokens',0))
        logging.debug('settled %s tokens order for player %s' % (tokens,player.key().name()))
        if getattr(player, 'credits'):
          player.credits += tokens
        else:
          player.credits = tokens
        player.put()
      elif type == product_types.RESOURCES:
        for name in [resource_types.CASH,resource_types.STEEL,resource_types.FUEL]:
          value = data.get(name,0)
          logging.debug('settled resource order for %s %s' % (value,name))
          has = getattr(player, name,0)  
          setattr(player, name, has + value)
        player.put()
      elif type == product_types.SPEED_UPS:
        component = Component.get_by_id(order_item['c_id'])
        logging.debug('settled speed up order for component %s' % component.key().id())
        model.completeBuilding(component)
    else:
      # may be refunded, canceled, log the activity
      result['content']['status'] = status
    return result