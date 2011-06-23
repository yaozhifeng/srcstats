from models import Project
from django.contrib import admin

class ProjectAdmin(admin.ModelAdmin):
    list_display = ['name', 'desc', 'repository', 'updatedate']
    

admin.site.register(Project, ProjectAdmin)
