# Copyright(C) 2012 Romain Bignon
#
# This file is part of a woob module.
#
# This woob module is free software: you can redistribute it and/or modify
# it under the terms of the GNU Lesser General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This woob module is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public License
# along with this woob module. If not, see <http://www.gnu.org/licenses/>.

# flake8: compatible

import json
import re
from io import BytesIO

from PIL import Image, ImageFilter

from woob.browser.filters.html import Attr, Link
from woob.browser.filters.json import Dict
from woob.browser.filters.standard import CleanText, Coalesce, Regexp
from woob.browser.pages import HTMLPage, JsonPage, LoggedPage, RawPage, XMLPage
from woob.capabilities import NotAvailable
from woob.capabilities.base import NotLoaded
from woob.exceptions import BrowserIncorrectPassword, BrowserUnavailable
from woob.tools.captcha.virtkeyboard import SplitKeyboard
from woob_modules.caissedepargne.pages import AuthenticationMethodPage as _AuthenticationMethodPage
from woob_modules.caissedepargne.pages import JsFilePage as _JsFilePage
from woob_modules.caissedepargne.pages import LoginTokensPage as _LoginTokensPage


class LoggedOut(Exception):
    pass


class BrokenPageError(Exception):
    pass


class BasePage:
    ENCODING = "iso-8859-15"

    def is_error(self):
        for script in self.doc.xpath("//script"):
            if script.text is not None and (
                "Le service est momentanément indisponible" in script.text
                or "Le service est temporairement indisponible" in script.text
                or "Votre abonnement ne vous permet pas d'accéder à ces services" in script.text
                or "Merci de bien vouloir nous en excuser" in script.text
            ):
                return True

        # sometimes the doc is a broken xhtml that fails to be parsed correctly
        if "Ressource indisponible" in self.text and "Le service est momentan&#233ment indisponible" in self.text:
            return True

        if "Ressource interdite" in self.text and "Vous ne pouvez acc&#233der &#224 cette page" in self.text:
            return True

        return False


class MyHTMLPage(BasePage, HTMLPage):
    def build_doc(self, data, *args, **kwargs):
        # XXX FUCKING HACK BECAUSE BANQUE POPULAIRE ARE NASTY AND INCLUDE NULL
        # BYTES IN DOCUMENTS.
        data = data.replace(b"\x00", b"")
        return super().build_doc(data, *args, **kwargs)


class RedirectErrorPage(HTMLPage):
    def is_unavailable(self):
        return bool(CleanText('//p[contains(text(), "momentanément indisponible")]')(self.doc))


class AuthorizeErrorPage(HTMLPage):
    def is_here(self):
        return CleanText('//p[contains(text(), "momentanément indisponible")]')(self.doc)

    def get_error_message(self):
        return CleanText('//p[contains(text(), "momentanément indisponible")]')(self.doc)


class ErrorPage(LoggedPage, MyHTMLPage):
    def on_load(self):
        if CleanText('//pre[contains(text(), "unexpected error")]')(self.doc):
            raise BrowserUnavailable("An unexpected error has occured.")
        if CleanText('//script[contains(text(), "momentanément indisponible")]')(self.doc):
            raise BrowserUnavailable("Le service est momentanément indisponible")
        elif CleanText('//h1[contains(text(), "Cette page est indisponible")]')(self.doc):
            raise BrowserUnavailable("Cette page est indisponible")
        return super().on_load()

    def get_token(self):
        try:
            buf = self.doc.xpath("//body/@onload")[0]
        except IndexError:
            return
        else:
            m = re.search(r"saveToken\('([^']+)'\)", buf)
            if m:
                return m.group(1)


class UnavailablePage(LoggedPage, MyHTMLPage):
    def on_load(self):
        h1 = CleanText("//h1[1]")(self.doc)
        if "est indisponible" in h1:
            raise BrowserUnavailable(h1)
        body = CleanText(".")(self.doc)
        if "An unexpected error has occurred." in body or "Une erreur s'est produite" in body:
            raise BrowserUnavailable(body)

        a = Link('//a[@class="btn"][1]', default=None)(self.doc)
        if not a:
            raise BrowserUnavailable()
        self.browser.location(a)


class NewLoginPage(HTMLPage):
    def get_main_js_file_url(self):
        return Attr('//script[contains(@src, "main-")]', "src")(self.doc)


class BaseJsFilePage(_JsFilePage):
    BPCE_RESOURCE_PATTERN = (
        r"https://www\.(?:rs|as)\-(?:ano|ext)\-bad\-(?:ib|ce)\.(?:banquepopulaire\.fr|caisse-epargne\.fr)"
    )

    def get_client_id_regexp(self):
        result = r'{url}/api/oauth/v2/token",resourceServerUrl:"{url}(?:[^"]*)",clientId:"([^"]+)"'.format(
            url=self.BPCE_RESOURCE_PATTERN
        )
        self.logger.debug("get_client_id_regexp(): %s", result)
        return result


class JsFilePage(BaseJsFilePage):
    def getChunkList(self):
        return re.findall(r"chunk-[A-Z0-9]{8}.js", self.text)

    def get_user_info_client_id(self):
        return Regexp(pattern=self.get_client_id_regexp()).filter(self.text)


class JsFilePageSeConnecterChunk(BaseJsFilePage):
    def contains_oauth_token_client_id(self):
        return bool(re.search(self.get_client_id_regexp(), self.text))

    def get_oauth_token_client_id(self):
        return Regexp(pattern=self.get_client_id_regexp()).filter(self.text)

    def get_oauth_autorize_client_id(self):
        return Regexp(pattern=r'authorizePath:"/api/oauth/v2/authorize",clientId:"([^"]+)"').filter(self.text)


class RootDashBoardPage(HTMLPage):
    def get_main_js_file_url_and_version(self):
        match = re.search(r"main-[A-Z0-9]{8}\.js\?v=\d+\.\d+\.\d+", self.text).group(0)
        if match:
            left_part, right_part = match.split("?v=")
            return left_part, right_part
        raise BrowserUnavailable("Could not find main js file url into RootDashBoardPage, please raise an issue")


class JsFilePageEspaceClient(_JsFilePage):
    def getChunkList(self):
        return re.findall(r"chunk-[A-Z0-9]{8}.js", self.text)


class JsFilePageEspaceClientChunk(_JsFilePage):
    def contains_client_id(self):
        return bool(re.search(r"[xXzZ]E=\"[a-z0-9-]{36}\"", self.text))

    def get_client_id(self):
        match_e = re.search(r"[xXzZ]E=\"[a-z0-9-]{36}\"", self.text).group(0)
        client_id = re.search(r"[a-z0-9-]{36}", match_e).group(0)
        return client_id


class KeysPage(JsonPage):
    def get_client_id(self):
        return Dict("#CLIENT_ID_PAS#")(self.doc)


class SeConnecterKeysPage(JsonPage):
    def get_ano_client_id(self):
        return Dict("#ANO_CLIENT_ID#")(self.doc)

    def get_ria_client_id(self):
        return Dict("#RIA_CLIENT_ID#")(self.doc)


class ConstPage(JsonPage):
    def get_client_id(self):
        return Dict("#CLIENT_PAS#")(self.doc)

    def get_client_iag(self):
        return Dict("#CLIENT_IAG#")(self.doc)


class SynthesePage(JsonPage):
    def get_raw_json(self):
        return self.text


class TransactionPage(JsonPage):
    def get_raw_json(self):
        return self.text


class AuthorizePage(JsonPage):
    def build_doc(self, content):
        # Sometimes we end up on this page but no
        # response body is given, so we get a decode error.
        # handle this page can assure the continuity of the login
        try:
            return super().build_doc(content)
        except ValueError:
            return {}

    def get_next_url(self):
        return Dict("action")(self.doc)

    def get_payload(self):
        return Dict("parameters/SAMLRequest")(self.doc)


class LoginTokensPage(_LoginTokensPage):
    def get_access_token(self):
        return Dict("parameters/access_token", default=None)(self.doc)

    def get_code(self):
        return Dict("parameters/code", default=None)(self.doc)

    def get_access_expire(self):
        return Dict("parameters/expires_in", default=None)(self.doc)


class InfoTokensPage(JsonPage):
    def get_access_token(self):
        value = Dict("access_token", default=None)(self.doc)
        return value

    def get_access_expire(self):
        value = Dict("expires_in", default=None)(self.doc)
        return value


class AuthenticationMethodPage(_AuthenticationMethodPage):
    def get_next_url(self):
        return Dict("response/saml2_post/action")(self.doc)

    def get_payload(self):
        return Dict("response/saml2_post/samlResponse", default=NotAvailable)(self.doc)

    def is_new_login(self):
        # We check here if we are doing a new login
        return bool(Dict("step/phase/state", default=NotAvailable)(self.doc))

    def get_status(self):
        return Dict("response/status", default=NotAvailable)(self.doc)

    def get_security_level(self):
        return Dict("step/phase/securityLevel", default="")(self.doc)

    def get_error_msg(self):
        return Coalesce(
            Dict("phase/notifications/0", default=None),
            Dict("phase/previousResult", default=None),
            Dict("response/status", default=None),
            default=None,
        )(self.doc)

    def login_errors(self, error, otp_type=None):
        """Adapted from caissedepargne: better handle wrong OTPs"""
        if error is None:
            # If the authentication failed, we don't have a status in the response
            error_msg = self.get_error_msg()
            if error_msg:
                if otp_type is not None:
                    if "otp_sms_invalid" in error_msg and otp_type == "SMS":
                        raise BrowserIncorrectPassword("Code SMS erroné")
                    if "FAILED_AUTHENTICATION" in error_msg and otp_type == "EMV":
                        raise BrowserIncorrectPassword("Code d'authentification erroné")
                raise AssertionError("Unhandled error message: %s" % error_msg)

        return super().login_errors(error)


class AuthenticationStepPage(AuthenticationMethodPage):
    def get_status(self):
        return Coalesce(Dict("response/status", default=NotAvailable), Dict("phase/state", default=NotAvailable))(
            self.doc
        )

    def get_next_url(self):
        return Dict("response/saml2_post/action")(self.doc)

    def get_payload(self):
        return Dict("response/saml2_post/samlResponse")(self.doc)

    def get_phone_number(self):
        return Dict(f"validationUnits/0/{self.validation_unit_id}/0/phoneNumber")(self.doc)

    def get_devices(self):
        return Dict(f"validationUnits/0/{self.validation_unit_id}/0/devices")(self.doc)

    def get_time_left(self):
        return Dict(f"validationUnits/0/{self.validation_unit_id}/0/requestTimeToLive")(self.doc)

    def authentication_status(self):
        return Dict("response/status", default=None)(self.doc)

    def is_authentication_successful(self):
        return Dict("response/status", default=None)(self.doc) == "AUTHENTICATION_SUCCESS"


class AppValidationPage(XMLPage):
    def get_status(self):
        return CleanText("//response/status")(self.doc)


class LoginPage(MyHTMLPage):
    def on_load(self):
        h1 = CleanText("//h1[1]")(self.doc)

        if h1.startswith("Le service est moment"):
            text = CleanText("//h4[1]")(self.doc) or h1
            raise BrowserUnavailable(text)

        if not self.browser.no_login:
            raise LoggedOut()


class BPOVirtKeyboard:
    """Virtual keyboard that uses OCR instead of hash matching."""

    codesep = " "

    def __init__(self, browser, images):
        import pytesseract
        from PIL import ImageOps

        self.char_to_code = {}
        whitelist = "-c tessedit_char_whitelist=0123456789"

        for img_item in images:
            img_content = browser.location(img_item["uri"]).content
            img = Image.open(BytesIO(img_content))
            img = img.filter(
                ImageFilter.UnsharpMask(radius=2, percent=150, threshold=3)
            )
            img = img.convert("L", dither=None)
            img = Image.eval(img, lambda x: 0 if x < 20 else 255)

            # Compute pixel density for disambiguation
            pixels = list(img.getdata())
            black_ratio = sum(1 for p in pixels if p == 0) / len(pixels)

            # Try multiple OCR strategies
            digit = None
            for prep in [
                img,
                img.resize((img.width * 3, img.height * 3), Image.NEAREST),
                ImageOps.expand(img, border=10, fill=255),
            ]:
                result = pytesseract.image_to_string(
                    prep, config=f"--psm 10 {whitelist}"
                ).strip()
                if result and len(result) == 1 and result in "0123456789":
                    digit = result
                    break

            # "1" is the thinnest digit; tesseract sometimes reads it as "4"
            if digit == "4" and black_ratio < 0.10:
                digit = "1"
            elif digit is None and black_ratio < 0.10:
                digit = "1"

            if digit is None:
                raise VirtKeyboardError(f"OCR failed for virtual keyboard image")

            self.char_to_code[digit] = img_item["value"]

    def get_string_code(self, password):
        symbols = []
        for c in password:
            symbols.append(self.char_to_code[c])
        return self.codesep.join(symbols)


class HomePage(LoggedPage, MyHTMLPage):
    # Sometimes, the page is empty but nothing is scrapped on it.
    def build_doc(self, data, *args, **kwargs):
        if not data:
            return None
        return super(MyHTMLPage, self).build_doc(data, *args, **kwargs)


class AccountsPage(LoggedPage, MyHTMLPage):
    pass


class LastConnectPage(LoggedPage, RawPage):
    pass


class CategoryPage(LoggedPage, RawPage):
    pass


class CategoryLoader:
    data = NotLoaded
    lookup = NotLoaded

    def load(self, json_content):
        self.data = json.loads(json_content)
        lt = {}

        def visit(categories):
            for cat in categories:
                cid = cat.get("id")
                name = cat.get("name")
                if cid is not None and name is not None:
                    lt[cid] = name
                if "children" in cat and cat["children"]:
                    visit(cat["children"])

        visit(self.data.get("data", []))
        self.lookup = lt

    def get_name_by_id(self, target_id):
        if self.lookup == NotLoaded:
            raise ValueError("Data not loaded. Call load() first.")
        return self.lookup.get(target_id)
