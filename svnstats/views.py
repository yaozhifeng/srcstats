# Create your views here.
from django.http import HttpResponse
from django.template import RequestContext
from django.shortcuts import render_to_response, redirect
from django.db.models import Sum, Count

from models import Project, SVNLog, SVNLogDetail

def home(request):
    projects = Project.objects.values('name', 'desc').annotate(author_count=Count('svnlog__author', distinct=True))
    coders = SVNLog.objects.filter(commitdate__year=2011).values('author').annotate(linesadded=Sum('svnlogdetail__linesadded')).order_by('-linesadded')[:10]
    commits = SVNLog.objects.values('author', 'msg', 'commitdate', 'project__name').order_by('-commitdate')[:10]
    return render_to_response('home.html',
                    {
                        'projects': projects,
                        'coders': coders,
                        'commits': commits,
                    },
                    context_instance = RequestContext(request)
                    )
