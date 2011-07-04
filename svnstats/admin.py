from models import Project, SVNLog, SVNAuthor
from django.contrib import admin

class ProjectAdmin(admin.ModelAdmin):
    list_display = ['name', 'desc', 'repository', 'updatedate']
    actions = ['update']

    def update(self, request, queryset):
        for project in queryset:
            if not project.updating:
                project.update()

class SVNLogAdmin(admin.ModelAdmin):
    list_display = ['revno', 'author', 'commitdate']

class SVNAuthorAdmin(admin.ModelAdmin):
    list_display = ['author', 'display']

admin.site.register(Project, ProjectAdmin)
admin.site.register(SVNLog, SVNLogAdmin)
admin.site.register(SVNAuthor, SVNAuthorAdmin)

