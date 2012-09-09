#!/usr/bin/env python

import os
import webapp2
import jinja2
from google.appengine.ext import db

assets_path = os.path.join(os.path.dirname(__file__), 'static')

jinja_environment = jinja2.Environment(
    loader = jinja2.FileSystemLoader(assets_path))

class User(db.Expando):
  location = db.ListProperty(float)
  email = db.StringProperty()
  event = db.StringProperty()
  name = db.StringProperty()

class MapHandler(webapp2.RequestHandler):
  def get(self):
    template = jinja_environment.get_template("map.html")
    self.response.out.write(template.render({
        "moon":55
      }))

class MainHandler(webapp2.RequestHandler):
  def get(self):
    template = jinja_environment.get_template("index.html")
    self.response.out.write(template.render({}))

class LocationHandler(webapp2.RequestHandler):
  def get(self):
    self.response.out.write("your location is -80,-80")

app = webapp2.WSGIApplication(
  [('/', MainHandler),
    ('/', MapHandler),
    ('/lh', LocationHandler)
    ], debug = True)