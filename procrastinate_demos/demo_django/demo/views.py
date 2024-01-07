from django.views import generic

from . import models, tasks


class CreateBookView(generic.CreateView):
    model = models.Book
    fields = ["title", "author"]
    success_url = "/"

    def form_valid(self, form):
        response = super().form_valid(form)
        tasks.index_book.defer(book_id=self.object.id)
        return response


class ListBooksView(generic.ListView):
    model = models.Book
