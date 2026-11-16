"""
================================================================================
                    TEMP MAIL MODÜLÜ (temp.py)
   GELİŞTİRİCİ VE YAPAY ZEKA (AI) İÇİN KESİN SÖZLEŞME VE KURALLAR PROTOKOLÜ
================================================================================

[BU DOSYANIN AMACI]:
Bu dosya, CreativeLabs ana servislerindeki (service-frontier.py, service.py vb.)
geçici e-posta mantığını tamamen izole etmek için oluşturulmuştur.
İleride temp mail sağlayıcısını (API) değiştirmek istediğinizde ANA SERVİS KODLARINA
KESİNLİKLE DOKUNMAYACAKSINIZ. YALNIZCA BU DOSYAYI (temp.py) EDİTLEYECEKSİNİZ.

--------------------------------------------------------------------------------
[ANA SERVİS BU DOSYAYI NASIL KULLANIYOR? - ÇAĞRI AKIŞI]:
Ana servis içerisindeki `create_myedit_account()` fonksiyonu aynen şöyle çalışır:

    temp_mail = TempMailClient()
    email = temp_mail.get_email()
    # CyberLink signup(email, password) çağrılır...
    activation_url = temp_mail.wait_for_activation_link(timeout=60)
    activate_account(activation_url)  # Bu fonksiyon gelen URL'ye GET isteği atar!

--------------------------------------------------------------------------------
[YAPAY ZEKA / GELİŞTİRİCİ SÖZLEŞMESİ (FUNCTION RETURN CONTRACTS)]:
Yeni bir API entegre ettiğinizde aşağıdaki metotların isimleri, parametreleri
ve DÖNDÜRDÜKLERİ VERİ FORMATI BİREBİR AYNI KALMALIDIR:

1. `get_email(self, length=10, domain=None, ...) -> str`
   - DÖNÜŞ DEĞERİ: Sadece string e-posta adresi (örn: "decentsea48@zzzzig.com")
   - DİKKAT: Sözlük, tuple veya nesne DÖNMEMELİDİR. Sadece e-posta `str` dönmelidir.
   - ÖZNİTELİKLER: `self.email = email` ve `self.address = email` olarak atanmalıdır.
   - DOMAİN ZORUNLULUĞU: Gelen adres `@zzzzig.com` (veya WHITELIST_DOMAINS[0])
     değilse, doğru domain gelene kadar döngüyle tekrar istek atmalıdır.
   - KONSOL LOGU: `print(f"[Temp Mail] Olusturuldu: {self.email}")` basmalıdır.

2. `wait_for_activation_link(self, timeout=60, interval=3) -> str`
   - DÖNÜŞ DEĞERİ: CyberLink aktivasyon URL'si (`str`)
     (örn: "https://membership.cyberlink.com/prog/event/autoedm/trace_mem.jsp?..."
      veya "https://membership.cyberlink.com/prog/member/account-activate.do?...")
   - DİKKAT: Ana servis `activate_account(activation_url)` satırında bu dönen string
     URL'ye `requests.get(activation_url)` atar ve 200 HTTP kodu bekler.
     Dolayısıyla dönen şey tıklanabilir tam bir HTTP/HTTPS aktivasyon linki olmalıdır!
   - HATA DURUMU: Süre aşılırsa `raise TimeoutError("Aktivasyon maili gelmedi!")`

3. `wait_for_code(self, timeout=60, interval=3) -> str`
   - DÖNÜŞ DEĞERİ: Doğrulama kodu veya auth token (`str`)
     (örn: "7b7db8170a331a9fa78d31f2a008411ae1528239961e9f6b0a8639497eb4dc84" veya "123456")
   - HATA DURUMU: Süre aşılırsa `raise TimeoutError("Dogrulama kodu gelmedi!")`

4. DIŞARI AKTARILAN ZORUNLU SABİT VE ALIAS'LAR:
   - `WHITELIST_DOMAINS`: list, örn: `["zzzzig.com"]`
   - `POLL_COMPONENTS`: list, örn: `[]`
   - `generate_random_username(length=10) -> str`
   - `generate_random_name(length=10) -> str`
   - `TEMP_MAIL_PROXY_MODE`: int (1 = aktif, 0 = pasif)
   - `TEMP_MAIL_PROXY_CONFIG`: dict (proxy ayarları)
   - `apply_temp_mail_proxy(session)`: fonk
   - `PoofyMailClient = TempMailClient`: alias (eski servislerle uyumluluk için)

================================================================================
"""

import os
import re
import time
import random
import string
import urllib.parse
from typing import Optional, Union, List, Dict, Any
import requests

# ==============================================================================
# DOMAIN VE YARDIMCI SABİTLER
# ==============================================================================
# CyberLink ile stabil çalıştığı test edilen domainler listenin başındadır.
WHITELIST_DOMAINS = [
    "howtageek.com",
    "happypetcorner.com",
    "skinnytastea.com",
    "ambitiouskitchena.com",
    "bitesofwellnessa.com",
    "cottercruncha.com",
    "eatingbirdfooda.com",
    "foodfaithfitnessa.com",
    "foodpoliticsa.com",
    "healthyrecipesblogsa.com",
    "lizshealthytabla.com",
    "nutritionstrippeda.com",
    "thehealthymavena.com",
    "thekitchna.com",
    "verywellfita.com",
]

POLL_COMPONENTS = []


def generate_random_username(length: int = 10) -> str:
    """Belirtilen uzunlukta harf ve rakamlardan oluşan rastgele bir kullanıcı adı üretir."""
    chars = string.ascii_lowercase + string.digits
    return "".join(random.choices(chars, k=length))


def generate_random_name(length: int = 10) -> str:
    """Rastgele kullanıcı adı üretir (örn: u_7a8b9c)."""
    chars = string.ascii_lowercase + string.digits
    rand_suffix = "".join(random.choices(chars, k=length))
    return f"u_{rand_suffix}"


# ==============================================================================
# TEMP MAIL PROXY AYARLARI (Render.com 403 / Rate Limit Engeli İçin)
# ==============================================================================
# Render.com sunucularında IP engeline takılmamak için sadece temp mail isteklerine
# özel proxy alanı tanımlanmıştır. CyberLink veya görsel istekleri bu proxy'yi KULLANMAZ.
TEMP_MAIL_PROXY_MODE = 1

TEMP_MAIL_PROXY_CONFIG = {
    "http": "http://nrrbciri-1:5cauzsujeluf@p.webshare.io:80",
    "https": "http://nrrbciri-1:5cauzsujeluf@p.webshare.io:80",
}


def apply_temp_mail_proxy(session: requests.Session):
    """Sadece TempMailClient oturumuna proxy uygular."""
    if TEMP_MAIL_PROXY_MODE == 1 and TEMP_MAIL_PROXY_CONFIG:
        session.proxies.update(TEMP_MAIL_PROXY_CONFIG)


PROXY_MODE = TEMP_MAIL_PROXY_MODE
PROXY_CONFIG = TEMP_MAIL_PROXY_CONFIG


# ==============================================================================
# ANA GEÇİCİ E-POSTA İSTEMCİSİ (mail.howtageek.com)
# ==============================================================================
class TempMailClient:
    """mail.howtageek.com API Entegrasyonu"""

    BASE_URL = "https://mail.howtageek.com"

    def __init__(
        self,
        domain: Optional[str] = None,
        api_key: Optional[str] = None,
        proxy_mode: int = PROXY_MODE,
        proxy_config: Optional[dict] = None,
    ):
        if domain:
            self.domain = domain
        elif WHITELIST_DOMAINS:
            self.domain = WHITELIST_DOMAINS[0]
        else:
            self.domain = "howtageek.com"

        self.box = None
        self.email = None
        self.address = None
        self.token = None
        self.last_seq = 0
        self.session = requests.Session()
        self.session.headers.update({
            "accept": "application/json",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "referer": f"{self.BASE_URL}/",
        })
        apply_temp_mail_proxy(self.session)
        self._seen_ids = set()

    def get_available_domains(self) -> List[str]:
        """Kullanılabilir domain listesini döner."""
        return list(WHITELIST_DOMAINS)

    def get_email(
        self,
        length: Optional[int] = 10,
        domain: Optional[str] = None,
        local_part: Optional[Union[str, int]] = None,
    ) -> str:
        """
        Yeni bir geçici e-posta adresi üretir ve 'email@domain.com' string döner.
        İstenen domain gelene kadar tekrar istek atar.
        """
        if domain:
            self.domain = domain
        elif not self.domain and WHITELIST_DOMAINS:
            self.domain = WHITELIST_DOMAINS[0]

        target_domain = (self.domain or "howtageek.com").lstrip("@")
        target_suffix = "@" + target_domain

        while True:
            try:
                resp = self.session.get(
                    f"{self.BASE_URL}/session/reset",
                    params={"domain": target_domain},
                    timeout=15,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    email = data.get("address", "")

                    if email.endswith(target_suffix):
                        self.email = email
                        self.address = email
                        self.last_seq = 0
                        self._seen_ids.clear()
                        print(f"[Temp Mail] Olusturuldu: {self.email}")
                        return self.email
                time.sleep(0.5)
            except Exception as e:
                print(f"[Temp Mail] get_email uyarisi: {e}")
                time.sleep(1)

    def get_messages(self) -> List[Dict[str, Any]]:
        """Gelen kutusundaki mesajları listeler."""
        if not self.email:
            return []
        res = self.session.get(
            f"{self.BASE_URL}/messages/messagesAfter/{self.last_seq}",
            timeout=15,
        )
        if res.status_code == 200:
            data = res.json()
            messages = data.get("messages", [])
            if messages:
                self.last_seq = data.get("nextIndex", self.last_seq)
            return messages
        return []

    def get_message_detail(self, message_id: str) -> Dict[str, Any]:
        """Belirtilen mesajın detaylarını getirir."""
        if not self.email:
            return {}
        res = self.session.get(
            f"{self.BASE_URL}/messages/{message_id}",
            timeout=15,
        )
        if res.status_code == 200:
            msg_data = res.json().get("message", {})
            # Eski yapı ile tam uyumluluk için body_html ve body_text anahtarlarını da ekle
            if "html" in msg_data and "body_html" not in msg_data:
                msg_data["body_html"] = msg_data.get("html", "")
            if "text" in msg_data and "body_text" not in msg_data:
                msg_data["body_text"] = msg_data.get("text", "")
            return msg_data
        return {}

    def _extract_activation_link(self, text: str) -> Optional[str]:
        """CyberLink aktivasyon bağlantısını metin / HTML içerisinden ayıklar."""
        if not text:
            return None

        # 1. Doğrudan 'account-activate' içeren href linkini yakala
        matches = re.findall(
            r'href=[\'"](https?://[^\'"]*account-activate[^\'"]*)[\'"]',
            text,
            re.IGNORECASE,
        )

        # 2. Alternatif: metin içinde veya html içinde account-activate
        if not matches:
            matches = re.findall(
                r'(https?://[^\s\'"<>]*account-activate[^\s\'"<>]*)',
                text,
                re.IGNORECASE,
            )

        if matches:
            link = matches[0].replace("&amp;", "&").rstrip("\"'")
            # Eğer traceLink sarmalayıcısı ise içindeki asıl aktivasyon linkini çöz
            if "traceLink=" in link:
                parsed = urllib.parse.urlparse(link)
                qs = urllib.parse.parse_qs(parsed.query)
                if "traceLink" in qs and qs["traceLink"]:
                    return qs["traceLink"][0]
            return link

        # 3. Yedek: CyberLink trace_mem bağlantısı kontrolü
        pattern_trace = r'https?://membership\.cyberlink\.com/prog/event/autoedm/trace_mem\.jsp\?[^\s"\'<>]+'
        trace_links = re.findall(pattern_trace, text)
        for link in trace_links:
            link = link.replace("&amp;", "&").rstrip("\"'")
            if "traceLink=" in link:
                parsed = urllib.parse.urlparse(link)
                qs = urllib.parse.parse_qs(parsed.query)
                if "traceLink" in qs and qs["traceLink"]:
                    return qs["traceLink"][0]
            if any(k in link for k in ["account-activate", "Activate", "active-member"]):
                return link

        return None

    def _extract_code(self, text: str, detail_code: Optional[str] = None) -> Optional[str]:
        """Doğrulama kodunu (auth token veya sayısal OTP) ayıklar."""
        if not text:
            return None
        # 1. Auth token (CyberLink aktivasyon kodu / hash)
        auth_match = re.search(r"auth(?:%3D|=)([a-f0-9]{32,64})", text, re.I)
        if auth_match:
            return auth_match.group(1)
        # 2. Sayısal OTP kodu (6 haneli)
        otp_match = re.search(r"\b(\d{6})\b", text)
        if otp_match:
            return otp_match.group(1)
        # 3. Genel 4-8 haneli kod
        codes = re.findall(r"\b\d{4,8}\b", text)
        return codes[0] if codes else None

    def wait_for_message(self, timeout: int = 60, interval: int = 3) -> Dict[str, Any]:
        """Herhangi bir yeni mesaj gelene kadar bekler ve mesaj detayını döner."""
        print(f"[Temp Mail] Gelen kutusu sorgulanıyor ({self.email})...")
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                messages = self.get_messages()
                for msg in messages:
                    msg_id = msg.get("id")
                    if msg_id and msg_id not in self._seen_ids:
                        self._seen_ids.add(msg_id)
                        detail = self.get_message_detail(msg_id)
                        return detail or msg
            except Exception as e:
                print(f"[Temp Mail] Poll uyarısı: {e}")
            time.sleep(interval)
        raise TimeoutError("Mesaj gelmedi!")

    def wait_for_activation_link(self, timeout: int = 60, interval: int = 3) -> str:
        """
        CyberLink aktivasyon e-postasını bekler ve aktivasyon linki string URL döner.
        Ana servis bu linki alıp 'activate_account(activation_url)' fonksiyonuna iletir.
        """
        print(f"[Temp Mail] Gelen kutusu sorgulanıyor ({self.email})...")
        deadline = time.time() + timeout

        while time.time() < deadline:
            try:
                messages = self.get_messages()
                for msg in messages:
                    msg_id = msg.get("id")
                    if msg_id and msg_id not in self._seen_ids:
                        self._seen_ids.add(msg_id)
                        print(f"[+] Yeni mail alındı! ID: {msg_id}")
                        detail = self.get_message_detail(msg_id)
                        if detail:
                            html_content = detail.get("html") or detail.get("body_html") or ""
                            text_content = detail.get("text") or detail.get("body_text") or ""
                            content = html_content + "\n" + text_content
                            link = self._extract_activation_link(content)
                            if link:
                                print(f"  -> Aktivasyon linki bulundu: {link[:80]}...")
                                return link
            except Exception as e:
                print(f"[Temp Mail] Poll uyarısı: {e}")

            time.sleep(interval)

        raise TimeoutError("Aktivasyon maili gelmedi!")

    def wait_for_code(self, timeout: int = 60, interval: int = 3) -> str:
        """
        CyberLink doğrulama kodunu (auth token veya 6 haneli OTP) bekler ve string döner.
        """
        print(f"[Temp Mail] Kod bekleniyor ({self.email})...")
        deadline = time.time() + timeout

        while time.time() < deadline:
            try:
                messages = self.get_messages()
                for msg in messages:
                    msg_id = msg.get("id")
                    if msg_id and msg_id not in self._seen_ids:
                        self._seen_ids.add(msg_id)
                        print(f"[+] Yeni mail alındı! ID: {msg_id}")
                        detail = self.get_message_detail(msg_id)
                        if detail:
                            html_content = detail.get("html") or detail.get("body_html") or ""
                            text_content = detail.get("text") or detail.get("body_text") or ""
                            content = html_content + "\n" + text_content
                            code = self._extract_code(content)
                            if code:
                                print(f"[+] Doğrulama kodu bulundu: {code}")
                                return code
            except Exception as e:
                print(f"[Temp Mail] Poll uyarısı: {e}")

            time.sleep(interval)

        raise TimeoutError("Doğrulama kodu gelmedi!")


# Geriye dönük uyumluluk ve alternatif kullanım için alias:
PoofyMailClient = TempMailClient


if __name__ == "__main__":
    client = TempMailClient()
    email = client.get_email()
    print("=" * 60)
    print(f"Test Üretilen E-posta: {email}")
    print("=" * 60)
