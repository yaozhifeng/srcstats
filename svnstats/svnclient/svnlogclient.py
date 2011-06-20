'''
svnlogclient.py
Copyright (C) 2009 Nitin Bhide (nitinbhide@gmail.com)

This module is part of SVNPlot (http://code.google.com/p/svnplot) and is released under
the New BSD License: http://www.opensource.org/licenses/bsd-license.php
--------------------------------------------------------------------------------------

A convinience wrapper over the subversion client to query the log information
'''

import logging
import datetime, time
import os, re, string
import urllib, urlparse
import getpass
import traceback
import types
import tempfile
from os.path import normpath
from operator import itemgetter
from StringIO import StringIO
import pysvn

SVN_HEADER_ENCODING = 'utf-8'
URL_NORM_RE = re.compile('[/]+')

def convert2datetime(seconds):
    gmt = time.gmtime(seconds)
    return(datetime.datetime(gmt.tm_year, gmt.tm_mon, gmt.tm_mday, gmt.tm_hour, gmt.tm_min, gmt.tm_sec))

def makeunicode(s):
    uns = s
    
    if(s):
        encoding = 'utf-8'
        errors='strict'
        if not isinstance(s, unicode):
            try:
                #try utf-8 first.If that doesnot work, then try 'latin_1'
                uns=unicode(s, encoding, errors)
            except UnicodeDecodeError:
                uns=unicode(s, 'latin_1', errors)
        assert(isinstance(uns, unicode))
    return(uns)
    
def normurlpath(pathstr):
    '''
    normalize url path. I cannot use 'normpath' directory as it changes path seperator to 'os' default path seperator.
    '''
    nrmpath = pathstr
    if( nrmpath):
        nrmpath = re.sub(URL_NORM_RE, '/',nrmpath)
        nrmpath = makeunicode(nrmpath)
        assert(nrmpath.endswith('/') == pathstr.endswith('/'))
        
    return(nrmpath)
    
def getDiffLineCountDict(diff_log):
    diff_log = makeunicode(diff_log)
    diffio = StringIO(diff_log)
    addlnCount=0
    dellnCount=0
    curfile=None
    diffCountDict = dict()
    newfilediffstart = 'Index: '
    newfilepropdiffstart = 'Property changes on: '
    for diffline in diffio:
        #remove the newline characters near the end of line
        diffline = diffline.rstrip()
        if(diffline.find(newfilediffstart)==0):
            #diff for new file has started update the old filename.
            if(curfile != None):
                diffCountDict[curfile] = (addlnCount, dellnCount)
            #reset the linecounts and current filename
            addlnCount = 0
            dellnCount = 0
            #Index line entry doesnot have '/' as start of file path. Hence add the '/'
            #so that path entries in revision log list match with the names in the 'diff count' dictionary
            logging.debug(diffline)
            curfile = u'/'+diffline[len(newfilediffstart):]
        elif(diffline.find(newfilepropdiffstart)==0):
            #property modification diff has started. Ignore it.
            if(curfile != None):
                diffCountDict[curfile] = (addlnCount, dellnCount)
            curfile = u'/'+diffline[len(newfilepropdiffstart):]
            #only properties are modified. there is no content change. hence set the line count to 0,0
            if( curfile not in diffCountDict):
                diffCountDict[curfile] = (0, 0)
        elif(diffline.find('---')==0 or diffline.find('+++')==0 or diffline.find('@@')==0 or diffline.find('===')==0):                
            continue
        elif(diffline.find('-')==0):
            dellnCount = dellnCount+1                
        elif(diffline.find('+')==0):
             addlnCount = addlnCount+1
    
    #update last file stat in the dictionary.
    if( curfile != None):
        diffCountDict[curfile] = (addlnCount, dellnCount)
    return(diffCountDict)
    
class SVNLogClient:
    def __init__(self, svnrepourl,binaryext=[], username=None,password=None):
        self.svnrooturl = None
        self.tmppath = None
        self.username = None
        self.password = None
        self._updateTempPath()
        self.svnrepourl = svnrepourl
        self.svnclient = pysvn.Client()
        self.svnclient.exception_style = 1
        self.svnclient.callback_get_login = self.get_login
        self.svnclient.callback_ssl_server_trust_prompt = self.ssl_server_trust_prompt
        self.svnclient.callback_ssl_client_cert_password_prompt = self.ssl_client_cert_password_prompt
        self.setbinextlist(binaryext)
        self.set_user_password(username, password)
        
    def setbinextlist(self, binextlist):
        '''
        set extensionlist for binary files with some cleanup if required.
        '''
        binaryextlist = []
        for binext in binextlist:
            binext = binext.strip()
            binext = u'.' + binext
            binaryextlist.append(binext)
            binext = binext.upper()
            binaryextlist.append(binext)
        self.binaryextlist = tuple(binaryextlist)

    def set_user_password(self,username, password):
        if( username != None and username != u''):
            self.username = username
            self.svnclient.set_default_username(self.username)
        if( password != None):
            self.password = password
            self.svnclient.set_default_password(self.password)
        
    def get_login(self, realm, username, may_save):
        logging.debug("This is a svnclient.callback_get_login event. ")
        if( self.username == None):
            self.username = raw_input("username for %s:" % realm)
        #save = True
        if( self.password == None):
            self.password = getpass.getpass()
        if(self.username== None or self.username ==''): 
            retcode = False
        else:
            retcode = True
        return retcode, self.username, self.password, may_save

    def ssl_server_trust_prompt( self, trust_dict ):
        retcode=True
        accepted_failures = 1
        save=1
        print "trusting: "
        print trust_dict
        return retcode, accepted_failures, save
        
    def ssl_client_cert_password_prompt(self, realm, may_save):
        """callback_ssl_client_cert_password_prompt is called each time subversion needs a password in the realm to use a client certificate and has no cached credentials. """
        logging.debug("callback_ssl_client_cert_password_prompt called to gain password for subversion in realm %s ." %(realm))
        password = getpass.getpass()
        return retcode, password, may_save    
    
    def _updateTempPath(self):
        #Get temp directory
        self.tmppath = tempfile.gettempdir()
        #Bugfix for line count update problems.
        #pysvn Client.diff() call documentation says
        #diff uses tmp_path to form the filename when creating any temporary files needed. The names are formed using tmp_path + unique_string + ".tmp".
        #For example tmp_path=/tmp/diff_prefix will create files like /tmp/diff_prefix.tmp and /tmp/diff_prefix1.tmp.
        #Hence i assumed that passing the temppath as '/tmp/svnplot' will create temporary files like '/tmp/svnplot1.tmp' etc.
        #However 'diff' function tries to create temporary files as '/tmp/svnplot/tempfile.tmp'. Since '/tmp/svnplot' folder doesnot exist
        #temporary file cannot be created and the 'diff' call fails. Hence I am changing it just 'tmpdir' path. -- Nitin (20 July 2009)
        #self.tmppath = os.path.join(self.tmppath, "svnplot")
        
    def printSvnErrorHint(self, exp):
        '''
        print some helpful error message for svn client errors.
        '''
        exitadvised = False
        if(isinstance(exp, pysvn.ClientError)):
            fullerrmsg, errs = exp
            for svnerr in errs:
                errmsg,code = svnerr
                logging.error("SVN Error Code %d" % code)
                logging.error(errmsg)
                print "SVN Error : "+errmsg
                helpmsg = None
                if( code == 22):
                    '''
                    Safe data 'Index: test' was followed by non-ASCII byte 196: unable to convert to/from UTF-8
                    '''
                    helpmsg ="HINT : Make sure that you have 'APR_ICONV_PATH' variable set to subversion client "
                    helpmsg = helpmsg +"'iconv' directory.\n"
                    if( 'APR_ICONV_PATH' in os.environ):
                        helpmsg = helpmsg+'Current value of APR_ICONV_PATH is %s' % os.environ['APR_ICONV_PATH']
                    else:
                        helpmsg = helpmsg+ 'Currently APR_ICONV_PATH is not set'
                    exitadvised=True
                elif (code == 145000):
                    '''
                    Unknown node kind error. Should never get this.
                    '''
                    helpmsg ="HINT : You should never get this error. Please report this to svnplot issue base"
                    exitadvised=True
                if( helpmsg):
                    print helpmsg
                    logging.error(helpmsg)
                    
        return(exitadvised)
        
    def getHeadRevNo(self):
        revno = 0
        headrev = self._getHeadRev()
        
        if( headrev != None):
            revno = headrev.revision.number
        else:
            print "Unable to find head revision for the repository"
            print "Check the firewall settings, network connection and repository path"
            
        return(revno)

    def _getHeadRev(self, enddate=None):
        rooturl = self.getRootUrl()
        logging.debug("Trying to get head revision rooturl:%s" % rooturl)
        
        headrevlog = None
        headrev = pysvn.Revision( pysvn.opt_revision_kind.head )
            
        revlog = self.svnclient.log( rooturl,
             revision_start=headrev, revision_end=headrev, discover_changed_paths=False)
                
        #got the revision log. Now break out the multi-try for loop
        if( revlog != None and len(revlog) > 0):
            revno = revlog[0].revision.number
            logging.debug("Found head revision %d" % revno)
            headrevlog = revlog[0]            
            
            if( enddate != None and enddate < headrevlog.date):
                headrevlog = self.getLastRevForDate(enddate, rooturl, False)
            
        return(headrevlog)
    
    def getStartEndRevForRepo(self, startdate=None, enddate=None):
        '''
        find the start and end revision data for the entire repository.
        '''
        rooturl = self.getRootUrl()
        headrev = self._getHeadRev(enddate)
        
        firstrev = self.getLog(1, url=rooturl, detailedLog=False)
        if (startdate!= None and firstrev.date < startdate):
            firstrev = self.getFirstRevForDate(startdate,rooturl,False)
            
        if( firstrev and headrev):            
            assert(firstrev.revision.number <= headrev.revision.number)
        
        return(firstrev, headrev)
        
    def findStartEndRev(self, startdate=None, enddate=None):
        #Find svn-root for the url
        url = self.getUrl('')
        
        #find the start and end revision numbers for the entire repository.
        firstrev, headrev = self.getStartEndRevForRepo(startdate, enddate)
        startrevno = firstrev.revision.number
        endrevno = headrev.revision.number
                
        if( not self.isRepoUrlSameAsRoot()):
            #if the url is not same as 'root' url. Then we need to find first revision for
            #given URL.        
        
            #headrev and first revision of the repository is found
            #actual start end revision numbers for given URL will be between these two numbers
            #Since svn log doesnot have a direct way of determining the start and end revisions
            #for a given url, I am using headrevision and first revision time to get those
            starttime = firstrev.date
            revstart = pysvn.Revision(pysvn.opt_revision_kind.date, starttime)
            logging.debug("finding start end revision for %s" % url)
            startrev = self.svnclient.log( url,
                         revision_start=revstart, revision_end=headrev.revision, limit = 1, discover_changed_paths=False)
            
            if( startrev != None and len(startrev) > 0):
                startrevno = startrev[0].revision.number
                
        return(startrevno, endrevno)
        
    def getFirstRevForDate(self, revdate, url, detailedlog=False):
        '''
        find the first log entry for the given date.
        '''
        revlog = None
        revstart = pysvn.Revision(pysvn.opt_revision_kind.date, revdate)
        revloglist = self.svnclient.log( url,
                         revision_start=revstart, limit = 1, discover_changed_paths=False)
        if( revloglist != None and len(revloglist) > 0):
            revlog = revloglist[0]
        return(revlog)
    
    def getLastRevForDate(self, revdate, url, detailedlog=False):
        '''
        find the first log entry for the given date.
        '''
        revlog = None
        revstart = pysvn.Revision(pysvn.opt_revision_kind.date, revdate)
        #seconds per day is 24*60*60. revend is revstart+1 day
        revend = pysvn.Revision(pysvn.opt_revision_kind.date, revdate+(24*60*60))
        revloglist = self.svnclient.log( url,
                         revision_start=revstart, revision_end=revend, discover_changed_paths=False)
        if( revloglist != None and len(revloglist) > 0):
            revlog = revloglist[-1]
        return(revlog)
        
    def getLog(self, revno, url=None, detailedLog=False):
        log=None
        if( url == None):
            url = self.getUrl('')
        rev = pysvn.Revision(pysvn.opt_revision_kind.number, revno)
                
        logging.debug("Trying to get revision log. revno:%d, url=%s" % (revno, url))
        revlog = self.svnclient.log( url,
             revision_start=rev, revision_end=rev, discover_changed_paths=detailedLog)
        log = revlog[0]
                
        return(log)

    def getLogs(self, startrevno, endrevno, cachesize=1, detailedLog=False):
        revlog =None
        startrev = pysvn.Revision(pysvn.opt_revision_kind.number, startrevno)
        endrev = pysvn.Revision(pysvn.opt_revision_kind.number, endrevno)
        url = self.getUrl('')
                
        logging.debug("Trying to get revision logs [%d:%d]" % (startrevno, endrevno))
        revlog = self.svnclient.log( url,
             revision_start=startrev, revision_end=endrev, limit=cachesize,
                                     discover_changed_paths=detailedLog)
        return(revlog)
    
    def getRevDiff(self, revno):
        rev1 = pysvn.Revision(pysvn.opt_revision_kind.number, revno-1)
        rev2 = pysvn.Revision(pysvn.opt_revision_kind.number, revno)
        url = self.getUrl('')
        diff_log = None
        
        logging.info("Trying to get revision diffs url:%s" % url)
        diff_log = self.svnclient.diff(self.tmppath, url, revision1=rev1, revision2=rev2,
                        recurse=True,ignore_ancestry=True,ignore_content_type=False,
                        header_encoding=SVN_HEADER_ENCODING, diff_deleted=True)
                    
        return diff_log

    def getRevFileDiff(self, path, revno,prev_path=None,prev_rev_no=None):
        if( prev_path == None):
            prev_path = path

        if( prev_rev_no == None):
            prev_rev_no = revno-1
            
        cur_url = self.getUrl(path)
        cur_rev = pysvn.Revision(pysvn.opt_revision_kind.number, revno)
        prev_url = self.getUrl(prev_path)
        prev_rev = pysvn.Revision(pysvn.opt_revision_kind.number, prev_rev_no)
        diff_log = None
        
        logging.debug("Getting filelevel revision diffs")
        logging.debug("revision : %d, url=%s" % (revno, cur_url))
        logging.debug("prev url=%s" % prev_url)
        
        try:
            diff_log = self.svnclient.diff(self.tmppath, url_or_path=prev_url, revision1=prev_rev,
                        url_or_path2=cur_url , revision2=cur_rev,
                        recurse=True, ignore_ancestry=False,ignore_content_type=False,
                        header_encoding=SVN_HEADER_ENCODING, diff_deleted=True)
        except pysvn.ClientError, exp:
            logging.exception("Error in getting file level revision diff")
            logging.debug("url : %s" % cur_url)
            logging.debug("previous url : %s" % prev_url)
            logging.debug("revno =%d", revno)
            logging.debug("prev renvo = %d", prev_rev_no)            
            raise
        
        return(diff_log)
    
    def getInfo(self, path, revno=None):
        '''Gets the information about the given path ONLY from the repository.
        Hence recurse flag is set to False.
        '''
        if( revno == None):
            rev = pysvn.Revision( pysvn.opt_revision_kind.head )
        else:
            rev = pysvn.Revision(pysvn.opt_revision_kind.number, revno)
        url = self.getUrl(path)
        entry_list = None
        
        logging.debug("Trying to get file information for %s" % url)
        entry_list = self.svnclient.info2( url,revision=rev,recurse=False)
        
        return(entry_list)
        
    def getFullDirInfo(self, path, revno):
        '''
        get full information of the directory at this given path and given revision
        number. It is assumed that 'path' represents a directory.
        '''
        if( revno == None):
            rev = pysvn.Revision( pysvn.opt_revision_kind.head )
        else:
            rev = pysvn.Revision(pysvn.opt_revision_kind.number, revno)
        url = self.getUrl(path)
        entry_list = None
        
        logging.debug("Trying to get full information for %s" % url)
        entry_list = self.svnclient.info2( url,revision=rev,recurse=True)
        
        return(entry_list)
    
    def getFileList(self, path, revno):
        '''
        return the file list of all the files in the directory 'path' and its
        sub directories
        '''                
        entrylist = self.getFullDirInfo(path, revno)
        dirpath = path
        if not dirpath.endswith('/'):
            dirpath = path + '/'
        assert(dirpath.endswith('/'))
        for pathentry, info_dict in entrylist:
            if info_dict.kind == pysvn.node_kind.file:
                yield normurlpath(dirpath+pathentry)
        
        
    def isChildPath(self, filepath):
        '''
        Check if the given path is a child path of if given svnrepourl. All filepaths are child paths
        if the repository path is same is repository 'root'
        Use while updating/returning changed paths in the a given revision.
        '''
        assert(self.svnrooturl != None)
        fullpath = self.svnrooturl + filepath
                
        return(fullpath.startswith(self.svnrepourl))

    def __isBinaryFileExt(self, filepath):
        '''
        check the extension of filepath and see if the extension is in binary files
        list
        '''
        return(filepath.endswith(self.binaryextlist))        

    def __isTextMimeType(self, fmimetype):
        '''
        check if the mime-type is a text mime-type based on the standard svn text file logic.        
        '''
        textMimeType = False
        if( fmimetype.startswith('text/') or fmimetype == 'image/x-xbitmap' or fmimetype == 'image/x-xpixmap'):
            textMimeType = True
        return(textMimeType)
            
    def __isBinaryFile(self, filepath, revno):
        '''
        detect if file is a binary file using same heuristic as subversion. If the file
        has no svn:mime-type  property, or has a mime-type that is textual (e.g. text/*),
        Subversion assumes it is text. Otherwise it is treated as binary file.
        '''
        logging.debug("Binary file check for file <%s> revision:%d" % (filepath, revno))
        binary = False #if explicit mime-type is not found always treat the file as 'text'                   
        url = self.getUrl(filepath)
        rev = pysvn.Revision(pysvn.opt_revision_kind.number, revno)

        proplist = self.svnclient.proplist(url, revision=rev)        
        if( len(proplist) > 0):
            assert(len(proplist) == 1)
            path, propdict = proplist[0]
            if( 'svn:mime-type' in propdict):
                fmimetype = propdict['svn:mime-type']
                #print "found mime-type file: %s mimetype : %s" % (filepath, fmimetype)
                if( self.__isTextMimeType(fmimetype)==False):
                    #mime type is not a 'text' mime type.
                    binary = True
               
        return(binary)
    
    def isBinaryFile(self, filepath, revno):
        assert(filepath is not None)
        assert(revno > 0)
        binary = self.__isBinaryFileExt(filepath)
        
        if( binary == False):
            binary = self.__isBinaryFile(filepath, revno)
        return(binary)
    
    def isDirectory(self, revno, changepath):
        #if the file/dir is deleted in the current revision. Then the status needs to be checked for
        # one revision before that
        logging.debug("isDirectory: path %s revno %d" % (changepath, revno))
        isDir = False            
        
        try:
            entry = self.getInfo(changepath, revno)
            filename, info_dict = entry[0]
            if( info_dict.kind == pysvn.node_kind.dir):
                isDir = True
                logging.debug("path %s is Directory" % changepath)
        except pysvn.ClientError, expinst:
            #it is possible that changedpath is deleted (even if changetype is not 'D') and
            # doesnot exist in the revno. In this case, we will get a ClientError exception.
            # this case just return isDir as 'False' and let the processing continue
            pass
                                                    
        return(isDir)
        
    def _getLineCount(self, filepath, revno):
        linecount = 0
        
        logging.info("Trying to get linecount for %s" % (filepath))
        rev = pysvn.Revision(pysvn.opt_revision_kind.number, revno)
        url = self.getUrl(filepath)
        contents = self.svnclient.cat(url, revision = rev)
        matches = re.findall("$", contents, re.M )
        if( matches != None):
            linecount = len(matches)
        logging.debug("%s linecount : %d" % (filepath, linecount))
        
        return(linecount)
    
    def getLineCount(self, filepath, revno):
        linecount = 0        
        if( self.isBinaryFile(filepath, revno) == False):
            linecount = self._getLineCount(filepath, revno)
        
        return(linecount)

    def getRootUrl2(self):
        assert( self.svnrooturl == None)
        #remove the trailing '/' if any
        firstrev = pysvn.Revision( pysvn.opt_revision_kind.number, 1)
        possibleroot = self.svnrepourl        
        if( possibleroot.endswith('/') == False):
            possibleroot = possibleroot+'/'
        #get the last log message for the given path.
        headrev = pysvn.Revision( pysvn.opt_revision_kind.head )
        urlinfo = self.svnclient.info2( possibleroot,revision=headrev,recurse=False)
        last_changed_rev = headrev
        maxmatchlen = 0
        for path, infodict in urlinfo:
            self.svnrooturl = infodict.repos_root_URL
            break
                                
    def getRootUrl(self):        
        if( self.svnrooturl == None and self.svnclient.is_url(self.svnrepourl)):
            # for some reason 'root_url_from_path' crashes Python interpreter
            # for http:// urls for PySVN 1.6.3 (python 2.5)
            # hence I need to do jump through hoops to get -- Nitin
            #self.svnrooturl = self.svnclient.root_url_from_path(self.svnrepourl)
            
            #Comment this line if PySVN - root_url_from_path() function works for you.
            self.getRootUrl2()
            
            logging.debug("found rooturl %s" % self.svnrooturl)
            
        #if the svnrooturl is None at this point, then raise an exception
        if( self.svnrooturl == None):
            raise RuntimeError , "Repository Root not found"
            
        return(self.svnrooturl)
    
    def getUrl(self, path):
        url = self.svnrepourl
        if( path.strip() != ""):
            #remember 'path' can be a unicode string            
            try:
                path = path.encode('utf8')
            except:
                #not possible to encode path as unicode. Probably an latin-1 character with value > 127
                #keep path as it is.
                pass
            url = self.getRootUrl() + urllib.pathname2url(path)
        return(url)

    def isRepoUrlSameAsRoot(self):
        repourl = self.svnrepourl.rstrip('/')
        rooturl = self.getRootUrl()
        rooturl = rooturl.rstrip('/')
        return(repourl == rooturl)
    
    def __iter__(self):
        from svnlogiter import SVNRevLogIter
        return(SVNRevLogIter(self, 1, self.getHeadRevNo()))

