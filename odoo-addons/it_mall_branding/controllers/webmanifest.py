from odoo.addons.web.controllers.webmanifest import WebManifest as OriginalWebManifest

class WebManifest(OriginalWebManifest):
    def _get_webmanifest(self):
        result = super()._get_webmanifest()
        result['background_color'] = '#00e5ff'
        result['theme_color'] = '#00e5ff'
        return result