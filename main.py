#!/usr/bin/env python
import os
from uuid import uuid4
import webapp2
import jinja2
from google.appengine.ext import db
from hangout import AuthFactory


assets_path = os.path.join(os.path.dirname(__file__), 'views')
jinja = jinja2.Environment(
    loader = jinja2.FileSystemLoader(assets_path))

class BaseHandler(webapp2.RequestHandler):
  csrf_protect = True
  view = 'base.html'

  def initialize(self, request, response):
    webapp2.RequestHandler.initialize(self, request, response)

  def init_csrf(self):
    """Issue and handle CSRF token as necessary"""
    self.csrf_token = self.request.cookies.get(u'c')
    if not self.csrf_token:
      self.csrf_token = str(uuid4())[:8]
      self.set_cookie('c', self.csrf_token)
    if self.request.method == u'POST' and self.csrf_protect and \
      self.csrf_token != self.request.POST.get(u'_csrf_token'):
      raise Exception(u'Missing or invalid CSRF token')

  def set_cookie(self, name, value, expires = None):
    """Set a cookie"""
    import datetime
    import Cookie
    if value is None:
      value = 'deleted'
      expires = datetime.timedelta(minutes = -50000)
    jar = Cookie.SimpleCookie()
    jar[name] = value
    jar[name]['path'] = u'/'
    if expires:
      if isinstance(expires, datetime.timedelta):
          expires = datetime.datetime.now() + expires
      if isinstance(expires, datetime.datetime):
          expires = expires.strftime('%a, %d %b %Y %H:%M:%S')
      jar[name]['expires'] = expires
    self.response.headers.add_header(*jar.output().split(': ', 1))

  def get(self):
    pass

  def render(self, view, data = None):
    template = jinja.get_template(view + ".html")
    if not data:
      data = {}
    self.response.out.write(template.render(data))


class FacebookHandler(BaseHandler):
  csrf_protect = False

  @AuthFactory.FacebookAuth
  def get(self):
    if self.user:
      self.render(self.view, {
        'user':{
          "name":self.user.name,
          "pic":self.user.pic
          }
      })
    else:
      from gaesessions import get_current_session
      self.render("login", {
        'host':self.request.application_url + '/',
        'fb_auth_state':get_current_session()['fb_auth_state']
        })


class MainHandler(FacebookHandler):
  def initialize(self, request, response):
    FacebookHandler.initialize(self, request, response)
    self.view = 'create_or_repeat'


app = webapp2.WSGIApplication(
  [(r'/', MainHandler),
    (r'/lh/.*', FacebookHandler)
    ], debug = True)