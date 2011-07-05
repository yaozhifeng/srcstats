# Create your views here.
from django.http import HttpResponse
from django.template import RequestContext
from django.shortcuts import render_to_response, redirect
from django.db.models import Sum, Count
import datetime

from models import Project, SVNLog, SVNLogDetail
from dbviews import AuthorContrib

def home(request):
    projects = Project.objects.values('name', 'desc')
    projects = projects.annotate(author_count=Count('svnlog__author', distinct=True))

    #calculate day of one week ago
    today = datetime.date.today()
    lastweekday = today - datetime.timedelta(days=7)
    lastmonthday = today - datetime.timedelta(days=30)
    print 'stats week range: %s - %s' % (lastweekday.isoformat(), today.isoformat())
    print 'stats month range: %s - %s' % (lastmonthday.isoformat(), today.isoformat())
    
    coders = AuthorContrib.objects.filter(commitdate__range=(lastmonthday, today))
    coders = coders.values('author', 'display').annotate(linesadded=Sum('linesadded'))
    coders = coders.annotate(linesdeleted=Sum('linesdeleted'))
    coders = coders.order_by('-linesadded','-linesdeleted')[:10]

    coders_w = AuthorContrib.objects.filter(commitdate__range=(lastweekday, today))
    coders_w = coders_w.values('author', 'display').annotate(linesadded=Sum('linesadded'))
    coders_w = coders_w.annotate(linesdeleted=Sum('linesdeleted'))
    coders_w = coders_w.order_by('-linesadded', '-linesdeleted')[:10]

    commits = SVNLog.objects.values('author', 'msg', 'commitdate', 'project__name').order_by('-commitdate')[:6]
    return render_to_response('home.html',
                    {
                        'projects': projects,
                        'coders_week': coders_w,
                        'coders_month': coders,
                        'commits': commits,
                    },
                    context_instance = RequestContext(request)
                    )
