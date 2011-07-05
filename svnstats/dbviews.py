from django.db import models
from django.utils.translation import ugettext_lazy as _

#view table
class AuthorContrib(models.Model):
    author = models.CharField(_('author'), max_length=50)
    display = models.CharField(_('display'), max_length=20)
    msg = models.TextField(_('commit comment'))
    commitdate = models.DateTimeField(_('commit date'))
    linesadded = models.IntegerField(_('lines added'))
    linesdeleted = models.IntegerField(_('lines deleted'))

    class Meta:
        db_table = 'view_authorcontrib'
