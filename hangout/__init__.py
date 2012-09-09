from hangout.settings import facebook_creds as creds
from facebook import Facebook
from google.appengine.ext import db


class User(db.Model):
  name = db.StringProperty()
  email = db.StringProperty()
  location = db.GeoPtProperty()
  pic = db.StringProperty()


class AuthFactory(object):
  # TODO: begin auth/verify auth needed
  @staticmethod
  def FacebookAuth(func):
    def authenticated_request_method(self, *args, **kw):
      from gaesessions import get_current_session
      session = get_current_session()
      self.user = None
      self.fb = Facebook(creds['AppSecret'], creds['AppID'])
      if session.has_key('fb_auth_state') and session['fb_auth_state'] == self.request.get('state'):
        if self.fb.exchange_code_for_auth_token(self.request):
          session.terminate()
          session = get_current_session()
          session['uid'] = 'F' + self.fb.uid
          self.user = UserFactory.getFacebookUser(self.fb)
      else:
        if session.has_key('uid'):
          self.user = UserFactory.getFacebookUserById(session['uid'])
        elif not self.fb.check_authentication(self.request):
          if session.is_active():
            session.terminate()
          import hashlib
          md5 = hashlib.md5()
          md5.update("cam is cool")
          session['fb_auth_state'] = md5.hexdigest()
        else:
          if not session.has_key('uid'):
            session['uid'] = 'F' + self.fb.uid
            self.user = UserFactory.getFacebookUser(self.fb)
      func(self, *args, **kw)
    return authenticated_request_method

class UserFactory(object):
  @staticmethod

  def getFacebookUserById(uid):
    return User.get_by_key_name(uid)

  @staticmethod
  def getFacebookUser(fb):
    key_name = 'F' + fb.uid
    user = User.get_by_key_name(key_name)
    if not user:
      me = fb.get_me()
      # fetch the user's info from facebook

      if not me:
        queries = {
            'me':'SELECT sex,first_name,pic_square FROM user WHERE uid=me()'
          }
        results = fb.fql_multiquery(queries)

        me = results['me']
      user = User(key_name = key_name)
      user.name = me['first_name']
      user.pic = me.get('pic_square', 'http://graph.facebook.com/' + me['username'] + '/picture')
      user.email = me['email']
      user.put()
    return user