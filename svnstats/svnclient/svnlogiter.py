'''
svnlogiter.py
Copyright (C) 2009 Nitin Bhide (nitinbhide@gmail.com)

This module is part of SVNPlot (http://code.google.com/p/svnplot) and is released under
the New BSD License: http://www.opensource.org/licenses/bsd-license.php
--------------------------------------------------------------------------------------

This file implements the iterators to iterate over the subversion log.
This is just a convinience interface over the pysvn module.

It is intended to be used in  python script to convert the Subversion log into
an sqlite database.
'''

import logging
import datetime, time
import os, re, string
import urllib, urlparse
import getpass
import tempfile
from operator import itemgetter
from StringIO import StringIO
from svnlogclient import *

class SVNRevLogIter:
    def __init__(self, logclient, startRevNo, endRevNo, cachesize=50):
        self.logclient = logclient
        self.startrev = startRevNo
        self.endrev = endRevNo
        self.revlogcache = None
        self.cachesize = cachesize
        
    def __iter__(self):
        return(self.next())

    def next(self):
        if( self.endrev == 0):
            self.endrev = self.logclient.getHeadRevNo()
        if( self.startrev == 0):
            self.startrev = self.endrev
        
        while (self.startrev < self.endrev):
            logging.info("updating logs %d to %d" % (self.startrev, self.endrev))
            self.revlogcache = self.logclient.getLogs(self.startrev, self.endrev,
                                                          cachesize=self.cachesize, detailedLog=True)
            if( self.revlogcache == None or len(self.revlogcache) == 0):
                raise StopIteration
            
            self.startrev = self.revlogcache[-1].revision.number+1
            for revlog in self.revlogcache:
                #since reach revision log entry is a dictionary. If the dictionary is empty
                #then log is not available or its end of log entries
                if( len(revlog) == 0):
                    raise StopIteration
                svnrevlog = SVNRevLog(self.logclient, revlog)
                yield svnrevlog

class SVNChangeEntry:
    '''
    one change log entry inside one revision log. One revision can contain multiple changes.
    '''
    def __init__(self, parent, changedpath):
        '''
        changedpath is one changed_path dictionary entry in values returned PySVN::Log calls
        '''
        self.parent = parent
        self.logclient = parent.logclient
        self.revno = parent.getRevNo()
        self.changedpath = changedpath
                
    def __updatePathType(self):
        '''
        Update the path type of change entry. 
        '''
        if( 'pathtype' not in self.changedpath):
            filepath = self.filepath()
            action = self.change_type()
            revno = self.revno
            if( action == 'D'):
                #if change type is 'D' then reduce the 'revno' to appropriately detect the binary file type.
                logging.debug("Found file deletion for <%s>" % filepath)
                filepath = self.prev_filepath()
                assert(filepath != None)            
                revno= self.prev_revno()
                
            #see if directory check is alredy done on this path. If not, then check with the repository        
            pathtype = 'F'
            if(self.logclient.isDirectory(revno, filepath) ==True):
                pathtype='D'
            self.changedpath['pathtype'] = pathtype
            #filepath may changed in case of 'delete' action.
            filepath = self.filepath()
            if( pathtype=='D' and not filepath.endswith('/')):
                #if it is directory then add trailing '/' to the path to denote the directory.
                self.changedpath['path'] = filepath + u'/'                
        
    def isValidChange(self):
        '''
        check the changed path is valid for the 'given' repository path. All paths are valid
        if the repository path is same is repository 'root'
        '''
        return(self.logclient.isChildPath(self.filepath()))
    
    def is_branchtag(self):
        '''
        Is this entry represent a branch or tag.
        '''
        branchtag = False
        if( self.changedpath['action']=='A'):        
            path = self.changedpath['copyfrom_path']
            rev  = self.changedpath['copyfrom_revision']
            if( path != None or rev != None):
                branchtag = True
        return(branchtag)
        
    def isDirectory(self):
        return(self.pathtype() == 'D')        

    def change_type(self):
        return(self.changedpath['action'])
    
    def filepath(self):
        fpath = normurlpath(self.changedpath['path'])
        return(fpath)
    
    def prev_filepath(self):
        prev_filepath = self.changedpath.get('copyfrom_path')
        if(prev_filepath ==None or len(prev_filepath) ==0):
            prev_filepath = self.filepath()
        return (prev_filepath)
        
    def prev_revno(self):
        prev_revno = self.changedpath.get('copyfrom_revision')
        if( prev_revno == None):
            prev_revno = self.revno-1
        else:
            assert(isinstance(prev_revno, type(pysvn.Revision(pysvn.opt_revision_kind.number, 0))))
            prev_revno = prev_revno.number
        
        return(prev_revno)
            
    def filepath_unicode(self):
        return(makeunicode(self.filepath()))

    def lc_added(self):
        lc = self.changedpath.get('lc_added', 0)
        return(lc)        

    def lc_deleted(self):
        lc = self.changedpath.get('lc_deleted', 0)
        return(lc)        

    def is_copied(self):
        '''
        return True if this change is copied from somewhere
        '''
        path = self.changedpath['copyfrom_path']
        rev  = self.changedpath['copyfrom_revision']
        is_copied=False
        if( path != None and len(path) > 0 and rev != None):
            is_copied=True
        return is_copied
    
    def copyfrom_path(self):
        '''
        get corrected copy from path.
        '''
        path = self.changedpath['copyfrom_path']
        if self.isDirectory() and path is not None and not path.endswith('/'):
            path = path + '/'
        return(makeunicode(path))
        
    def copyfrom(self):
        path = self.copyfrom_path()
        rev  = self.changedpath['copyfrom_revision']
        revno = None
        if( rev != None):
            assert(rev.kind == pysvn.opt_revision_kind.number)
            revno = rev.number
        
        return(path,revno)            

    def pathtype(self):
        '''
        path type is (F)ile or (D)irectory
        '''
        self.__updatePathType()
        pathtype = self.changedpath['pathtype']
        assert(pathtype == 'F' or (pathtype=='D' and self.filepath().endswith('/')))
        return(pathtype)

    def isBinaryFile(self):
        '''
        if the change is in a binary file.        
        '''        
        binary=False
        #check detailed binary check only if the change entry is of a file.
        if( self.pathtype() == 'F'):
            revno = self.revno
            filepath = self.filepath()
            
            if( self.change_type() == 'D'):
                #if change type is 'D' then reduce the 'revno' to appropriately detect the binary file type.
                logging.debug("Found file deletion for <%s>" % filepath)
                filepath = self.prev_filepath()
                revno= self.prev_revno()
            binary = self.logclient.isBinaryFile(filepath, revno)
            
        return(binary)    
                                           
    def updateDiffLineCountFromDict(self, diffCountDict):
        if( 'lc_added' not in self.changedpath):
            try:
                linesadded=0
                linesdeleted=0
                filename = self.filepath()
                
                if( diffCountDict!= None and filename in diffCountDict and not self.isBinaryFile()):
                    linesadded, linesdeleted = diffCountDict[filename]
                    self.changedpath['lc_added'] = linesadded
                    self.changedpath['lc_deleted'] = linesdeleted
            except:
                logging.exception("Diff Line error")
                raise
                
                    
    def getDiffLineCount(self):
        added = self.changedpath.get('lc_added', 0)
        deleted = self.changedpath.get('lc_deleted', 0)
            
        if( 'lc_added' not in self.changedpath):
            revno = self.revno
            filepath = self.filepath()
            changetype = self.change_type()
            prev_filepath = self.prev_filepath()
            prev_revno = self.prev_revno()
            filename = filepath

            if( self.isDirectory() == False and not self.isBinaryFile() ):
                #path is added or deleted. First check if the path is a directory. If path is not a directory
                # then process further.
                if( changetype == 'A'):
                    added = self.logclient.getLineCount(filepath, revno)
                elif( changetype == 'D'):
                    deleted = self.logclient.getLineCount(prev_filepath, prev_revno)
                elif (changetype == 'R'):
                    #change type 'R' (replace) means files contents are replaced hence
                    #calling self.__getDiffLineCount(filepath, revno,prev_filepath, prev_revno)
                    # will always return 0. In case 'R' there are two possibilities the
                    # the file path previously exists (in which case we need diff) or
                    # filepath is newly added (in which case we have to treat it as 'add')
                    try:
                        added, deleted = self.__getDiffLineCount(filepath, revno,None, None)
                    except:
                        added = self.logclient.getLineCount(filepath, revno)
                else:
                    #change type is 'changetype != 'A' and changetype != 'D'
                    #directory is modified
                    added, deleted = self.__getDiffLineCount(filepath, revno,prev_filepath, prev_revno)
                    
            logging.debug("DiffLineCount %d : %s : %s : %d : %d " % (revno, filename, changetype, added, deleted))
            self.changedpath['lc_added'] = added
            self.changedpath['lc_deleted'] = deleted
                  
        return(added, deleted)
    
    def __getDiffLineCount(self, filepath, revno, prev_filepath, prev_revno):
        diff_log = self.logclient.getRevFileDiff(filepath, revno,prev_filepath, prev_revno)
        diffDict = getDiffLineCountDict(diff_log)
        added=0
        deleted=0
        if( len(diffDict)==1):
            #for single files the 'diff_log' contains only the 'name of file' and not full path.
            #Hence to need to 'extract' the filename from full filepath
            filename = u'/'+filepath.rsplit(u'/', 2)[-1]
            fname, (added, deleted) = diffDict.popitem()
        return added, deleted
    
class SVNRevLog:
    def __init__(self, logclient, revnolog):
        self.logclient = logclient
        if( isinstance(revnolog, pysvn.PysvnLog) == False):
            self.revlog = self.logclient.getLog(revnolog, detailedLog=True)
        else:
            self.revlog = revnolog
        assert(self.revlog == None or isinstance(revnolog, pysvn.PysvnLog)==True)
        if( self.revlog):
            self.__normalizePaths()
            self.__updateCopyFromPaths()

    def isvalid(self):
        '''
        if the revision log is a valid log. Currently the log is invalid if the commit 'date' is not there.        
        '''
        valid = True
        if( self.__getattr__('date') == None):
            valid = False
        return(valid)

    def __normalizePaths(self):
        '''
        sometimes I get '//' in the file names. Normalize those names.
        '''
        assert(self.revlog is not None)
        for change in self.revlog.changed_paths:
            change['path'] = normurlpath(change['path'])
            assert('copyfrom_path' in change)
            change['copyfrom_path'] = normurlpath(change['copyfrom_path'])
        
    def __updateCopyFromPaths(self):
        '''
        If you create a branch/tag from the working copy and working copy has 'deleted files or directories.
        In this case, just lower revision number is not going to have that file in the same path and hence
        we will get 'unknown node kind' error. Hence we have to update the 'copy from path' and 'copy
        from revision' entries to the changed_path entries.
        Check Issue 44.
        '''
        assert( self.revlog is not None)
        #First check if there are any additions with 'copy_from'
        
        copyfrom = [(change['path'], change['copyfrom_path'], change['copyfrom_revision']) \
            for change in self.revlog.changed_paths \
                if( change['copyfrom_path'] != None and len(change['copyfrom_path']) > 0)]
        
        if( len(copyfrom) > 0):
            copyfrom = sorted(copyfrom, key=itemgetter(0), reverse=True)       
        
            for change in self.revlog.changed_paths:
                #check other modified or deleted paths (i.e. all actions other than add)
                if( change['action']!='A'):
                    curfilepath = change['path']
                    for curpath, copyfrompath, copyfromrev in copyfrom:
                        #change the curpath to 'directory name'. otherwise it doesnot make sense to add a copy path entry
                        #for example 'curpath' /trunk/xxx and there is also a deleted entry called '/trunk/xxxyyy'. then in such
                        #case don't replace the 'copyfrom_path'. replace it only if entry is '/trunk/xxx/yyy'
                        if(not curpath.endswith('/')):
                            curpath = curpath + '/'
                        if(curfilepath.startswith(curpath) and change['copyfrom_path'] is None):
                            #make sure that copyfrom path also ends with '/' since we are replacing directories
                            #curpath ends with '/'
                            if(not copyfrompath.endswith('/')):
                                copyfrompath = copyfrompath + '/'
                            assert(change['copyfrom_revision'] is None)
                            change['copyfrom_path'] = normurlpath(curfilepath.replace(curpath, copyfrompath,1))
                            change['copyfrom_revision'] = copyfromrev                    
                
    def getChangeEntries(self):
        '''
        get the change entries from each changed path entry
        '''        
        for change in self.revlog.changed_paths:
            change_entry = SVNChangeEntry(self, change)
            if( change_entry.isValidChange()):
                yield change_entry
    
    def getFileChangeEntries(self):
        '''
        filter the change entries to return only the file change entries.
        '''
        for change_entry in self.getChangeEntries():
            if change_entry.isDirectory() == False:
                yield change_entry
        
    def changedFileCount(self):
        '''includes directory and files. Initially I wanted to only add the changed file paths.
        however it is not possible to detect if the changed path is file or directory from the
        svn log output
        bChkIfDir -- If this flag is false, then treat all changed paths as files.
           since isDirectory function calls the svn client 'info' command, treating all changed
           paths as files will avoid calls to isDirectory function and speed up changed file count
           computations
        '''
        filesadded = 0
        fileschanged = 0
        filesdeleted = 0
        logging.debug("Changed path count : %d" % len(self.revlog.changed_paths))
        
        for change in self.getChangeEntries():
                isdir = change.isDirectory()
                if( isdir == False):
                    action = change.change_type()                
                    if(action == 'A'):
                        filesadded = filesadded+1
                    elif(action == 'D'):
                        filesdeleted = filesdeleted+1
                    else:
                        #action can be 'M' or 'R'
                        assert(action == 'M' or action=='R')
                        fileschanged = fileschanged +1
                    
        return(filesadded, fileschanged, filesdeleted)
                    
    def getDiffLineCount(self, bUpdLineCount=True):
        """
        Returns a list of tuples containing filename, lines added and lines modified
        In case of binary files, lines added and deleted are returned as zero.
        In case of directory also lines added and deleted are returned as zero
        """                        
        diffCountDict = None
        if( bUpdLineCount == True):
            diffCountDict = self.__updateDiffCount()
                    
        #get change entries sorted in the order of actions, and then paths.
        
        for change in self.getChangeEntries():
            change.updateDiffLineCountFromDict(diffCountDict)
            filename=change.filepath()
            changetype=change.change_type()
            linesadded=change.lc_added()
            linesdeleted = change.lc_deleted()
            logging.debug("%d : %s : %s : %d : %d " % (self.revno, filename, change.change_type(), linesadded, linesdeleted))
            yield change                    
    
    def getCopiedDirs(self):        
        '''
        return a list of change entries where directory is added/replaced during
        this revision changes.
        '''
        changelist = [change for change in self.getChangeEntries() \
                      if( change.is_copied() and change.isDirectory())]
        
        return changelist                
                
    def getDeletedDirs(self):
        '''
        return a list of change entries of where a directory is deleted
        '''
        changelist = [change for change in self.getChangeEntries() \
            if( change.isDirectory() and change.change_type()=='D')]
        return changelist
                
    def getRevNo(self):
        return(self.revlog.revision.number)
    
    def __getattr__(self, name):
        if(name == 'author'):
            author = ''
            #in case the author information is not available, then revlog object doesnot
            # contain 'author' attribute. This case needs to be handled. I am returning
            # empty string as author name.
            try:
                author =self.revlog.author
            except:
                pass
            return(author)
        elif(name == 'message'):
            msg = None
                
            try:
                msg = makeunicode(self.revlog.message)
            except:
                msg = u''
            return(msg)
        elif(name == 'date'):
            try:
                dt = convert2datetime(self.revlog.date)
            except:
                dt = None
            return(dt)
        elif(name == 'revno'):
            return(self.revlog.revision.number)
        elif(name == 'changedpathcount'):
            filesadded, fileschanged, filesdeleted = self.changedFileCount()
            return(filesadded+fileschanged+filesdeleted)
        return(None)
    
    def __useFileRevDiff(self):
        '''
        file level revision diff requires less memory but more calls to repository.
        Hence for large sized repositories, repository with many large commits, and
        repositories which are local file system, it is better to use file level revision
        diff. For other cases it is better to query diff of entire revision at a time.
        '''
        # repourl is not same as repository root (e.g. <root>/trunk) then we have to
        # use the file revision diffs.
        usefilerevdiff = True
        if( self.logclient.isRepoUrlSameAsRoot()):
            usefilerevdiff = False
        rooturl = self.logclient.getRootUrl()
        if( rooturl.startswith('file://')):
            usefilerevdiff=True
        if( not usefilerevdiff ):
            #check if there are additions or deletions. If yes, then use 'file level diff' to
            #avoid memory errors in large number of file additions or deletions.
            fadded, fchanged, fdeleted = self.changedFileCount()
            if( fadded > 1 or fdeleted > 1 or fchanged > 5):
                usefilerevdiff=True
        
        #For the time being always return True, as in case of 'revision level' diff filenames returned
        #in the diff are different than the filename returned by the svn log. hence this will result
        #wrong linecount computation. So far, I don't have good fix for this condition. Hence falling
        #back to using 'file level' diffs. This will result in multiple calls to repository and hence
        # will be slower but linecount data will be  more reliable. -- Nitin (15 Dec 2010)
        #usefilerevdiff=True
        return(usefilerevdiff)
        
    def __updateDiffCount(self):
        diffcountdict = dict()            
        try:
            revno = self.getRevNo()                            
            logging.debug("Updating line count for revision %d" % revno)
            if( self.__useFileRevDiff()):
                logging.debug("Using file level revision diff")
                for change in self.getChangeEntries():
                    filename = change.filepath()
                    diffcountdict[filename] = change.getDiffLineCount()
            else:                
                #if the svnrepourl and root url are same then we can use 'revision level' diff calls
                # get 'diff' of multiple files included in a 'revision' by a single svn api call.
                # As All the changes are 'modifications' (M type) then directly call the 'getRevDiff'.
                #getRevDiff fails if there are files added or 'deleted' and repository path is not
                # the root path.
                logging.debug("Using entire revision diff at a time")
                revdiff_log = self.logclient.getRevDiff(revno)                
                diffcountdict = getDiffLineCountDict(revdiff_log)
            
        except Exception, expinst:            
            logging.exception("Error in diffline count")
            raise
                        
        return(diffcountdict)
                 
