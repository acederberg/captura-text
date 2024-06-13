from app.views import AppView, BaseView


def captura_plugins(app_view: AppView):

    app = app_view.view_router
    app.include_router(TextView.view_router)
