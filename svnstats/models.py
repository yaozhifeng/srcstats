from django.db import models
from django.utils.translation import ugettext_lazy as _

# Create your models here.
class Project(models.Model):
    name = models.CharField(_('name'), max_length=50)
    desc = models.CharField(_('description'), max_length=250)
    repository = models.CharField(_('repository'), max_length=500)
    username = models.CharField(_('username'), max_length=50)
    password = models.CharField(_('password'), max_length=50)
    excludes = models.CharField(_('excluded paths'), max_length=500, null=True)
    updatedate = models.DateTimeField(_('update time'))

class SVNLog(models.Model):
    project = models.ForeignKey(Project)
    revno = models.IntegerField(_('revision number'))
    commitdate = models.DateTimeField(_('commit date'))
    author = models.CharField(_('author'), max_length=50)
    msg = models.TextField(_('commit comment'))
    addedfiles = models.IntegerField(_('added files'))
    changedfiles = models.IntegerField(_('changed files'))
    deletedfiles = models.IntegerField(_('deleted files'))

class SVNPath(models.Model):
    path = models.TextField(_('path'))

class SVNLogDetail(models.Model):
    svnlog = models.ForeignKey(SVNLog)
    changedpath = models.ForeignKey(SVNPath)
    copyfrompath = models.IntegerField(_('copyfrom'), null=True)
    copyfromrev = models.IntegerField(_('copy revision'), null=True)
    changetype = models.CharField(_('change type'), max_length=1)
    pathtype = models.CharField(_('path type'), max_length=1)
    linesadded = models.IntegerField(_('lines added'))
    linesdeleted = models.IntegerField(_('lines deleted'))
    entrytype = models.CharField(_('entry type'), max_length=1)

