from django.db import models
from django.db.models import Max, Min, Count, Avg
from django.utils.translation import ugettext_lazy as _
from svnclient.svnlogclient import SVNLogClient
from svnclient.svnlogiter import SVNRevLogIter

BINARYFILEXT = [ 'doc', 'xls', 'ppt', 'docx', 'xlsx', 'pptx', 'dot', 'dotx', 'ods', 'odm', 'odt', 'ott', 'pdf',
                 'o', 'a', 'obj', 'lib', 'dll', 'so', 'exe',
                 'jar', 'zip', 'z', 'gz', 'tar', 'rar','7z',
                 'pdb', 'idb', 'ilk', 'bsc', 'ncb', 'sbr', 'pch', 'ilk',
                 'bmp', 'dib', 'jpg', 'jpeg', 'png', 'gif', 'ico', 'pcd', 'wmf', 'emf', 'xcf', 'tiff', 'xpm',
                 'gho', 'mp3', 'wma', 'wmv','wav','avi'
                 ]



# Create your models here.
class Project(models.Model):
    name = models.CharField(_('name'), max_length=50)
    desc = models.CharField(_('description'), max_length=250)
    repository = models.CharField(_('repository'), max_length=500)
    username = models.CharField(_('username'), max_length=50)
    password = models.CharField(_('password'), max_length=50)
    excludes = models.CharField(_('excluded paths'), max_length=500, null=True)
    updatedate = models.DateTimeField(_('update time'))

    def update(self):
        '''
        update project statistics
        '''
        svnclient = SVNLogClient(self.repository, BINARYFILEXT, username=self.username, password=self.password)
        try:
            laststoredrev = self.getLastStoredRev()
            rootUrl = svnclient.getRootUrl()
            (startrevno, endrevno) = svnclient.findStartEndRev(None, None)
            startrevno = max(startrevno, laststoredrev+1)
            self.ConvertRevs(svnclient, startrevno, endrevno)
        except Exception as e:
            print 'Exception updating project'
            print e

    def ConvertRevs(self, svnclient, startrevno, endrevno):
        '''
        read svn repository, parse and save log details
        '''
        svnloglist = SVNRevLogIter(svnclient, startrevno, endrevno)
        revcount = 0
        lastrevno = 0

        for revlog in svnloglist:
            print revlog.message

    def getLastStoredRev(self):
        '''
        return the max revision number for the project
        '''
        try:
            revno = SVNLog.objects.filter(project=self).aggregate(Max('revno'))['revno__max']
        except:
            revno = 0

        return revno

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

