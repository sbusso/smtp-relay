'''
Created on Jun 13, 2011

@author: thatcherclay
'''

from zope.interface import implements

from twisted.internet import defer, threads
from twisted.mail import smtp
from twisted.python import failure, log
from twisted.mail.imap4 import LOGINCredentials, PLAINCredentials

from twisted.cred import credentials, checkers, error as credError
from twisted.cred.portal import IRealm
from twisted.cred.portal import Portal
from twisted.internet import ssl

import sys,os
sys.path.insert(0,os.getcwd()+"/output")
sys.path.insert(0,os.getcwd()+"/output/web")
os.environ['DJANGO_SETTINGS_MODULE'] = 'web.settings'
from web import settings
from django.contrib.auth.models import User, check_password

import logging

#from server.persistence import *
from server.messenger import SendGridMessenger, LocalhostMessenger, AuthenticatedMessenger
from server.message import SugarMessageDelivery, RedirectMessageDelivery


logger = logging.getLogger("sugar")
        
class SMTPRelaySMTPFactory(smtp.SMTPFactory):
    protocol = smtp.ESMTP
    
    def __init__(self, portal, ctx):
        smtp.SMTPFactory.__init__(self, portal)
        self.ctx = ctx

    def buildProtocol(self, addr):
        p = smtp.SMTPFactory.buildProtocol(self, addr)
        if self.ctx:
          p.ctx = self.ctx
        p.challengers = {"LOGIN": LOGINCredentials, "PLAIN": PLAINCredentials}
        return p

class SMTPRelayRealm:
    implements(IRealm)

    def __init__(self, *args, **kwargs):
        self.messenger = kwargs["messenger"]

    def requestAvatar(self, user, mind, *interfaces):
        if smtp.IMessageDelivery in interfaces:
            return smtp.IMessageDelivery, SugarMessageDelivery(user, self.messenger), lambda: None
        raise NotImplementedError()
        
class RedirectRealm:
    implements(IRealm)

    def __init__(self, *args, **kwargs):
        self.messenger = kwargs["messenger"]

    def requestAvatar(self, user, mind, *interfaces):
        if smtp.IMessageDelivery in interfaces:
            return smtp.IMessageDelivery, RedirectMessageDelivery(self.messenger), lambda: None
        raise NotImplementedError()
        

class DjangoAuthChecker:
    implements(checkers.ICredentialsChecker)
    credentialInterfaces = (credentials.IUsernamePassword,
                            credentials.IUsernameHashedPassword)
         
    def _checkPassword(self, user, password):
      if user.check_password(password):
        logger.info('Authorization passed for %s'%str(user))
        return user
      else:
        logger.warning('Unauthorized login: %s'% user)
        return failure.Failure(credError.UnauthorizedLogin())
    
    def _getUser(self, credentials):
      return User.objects.get(username=credentials.username)
 
    def requestAvatarId(self, credentials):            
        try:
            deferred = threads.deferToThread(self._getUser, credentials)
            deferred.addCallback(self._checkPassword, credentials.password)
            return deferred
        except:
            return defer.fail(credError.UnauthorizedLogin())