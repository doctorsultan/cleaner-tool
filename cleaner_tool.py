import base64
import json
import random
import re
import string
import time
import uuid
from urllib.parse import quote, unquote

import requests


def _rand_alpha(n: int) -> str:
    return "".join(random.choice(string.ascii_lowercase) for _ in range(n))


def _jitter(lo: float = 3.0, hi: float = 8.0):
    time.sleep(random.uniform(lo, hi))


def _backoff(attempt: int):
    t = min(60 * (2 ** attempt), 600)
    time.sleep(t + random.uniform(0, t * 0.2))


def _generate_ua() -> str:
    devices = [
        ("samsung", "SM-G998B"), ("samsung", "SM-A525F"),
        ("Xiaomi",  "M2101K6G"), ("OnePlus", "LE2115"),
    ]
    dpi        = random.choice(["420", "480", "560"])
    h          = random.choice([1080, 1440, 2400])
    av         = random.randint(29, 34)
    ar         = f"{random.randint(10,13)}.{random.randint(0,9)}"
    mfr, model = random.choice(devices)
    cpu        = _rand_alpha(2) + str(random.randrange(1000, 9999))
    ig         = random.choice(["276.0.0.26.110", "275.0.0.27.98", "274.0.0.26.105"])
    return (f"Instagram {ig} Android ({av}/{ar}; {dpi}dpi; 1080x{h}; "
            f"{mfr}; {model}; {cpu}; en_US)")


class CleanerTool:
    BLOKS_VER = "b3efaa0ec98aaa583cee9e7f624cd0737af0bab3ecda4cc2d468c973dd9f0db5"
    COMMENTS_BLOKS_VER = "f09100c88dd5cd7e4f18f79a0db55b2782dc884afee3af2bfb3c0c24da131857"

    def __init__(self, session_id: str):
        self.session_id       = session_id
        self._sess            = requests.Session()
        self._ua              = _generate_ua()
        self._device_id       = str(uuid.uuid4())
        self.user_id          = None
        self.username         = None
        self.total_unliked    = 0
        self.posts_unliked    = 0
        self.reels_unliked    = 0
        self.total_unreposted = 0
        self.total_unsaved    = 0
        self.total_comments_deleted = 0

    def _report(self, text: str):
        print(text)

    def _progress(self, label: str, count: int):
        print(f"\r{label}: {count}", end="", flush=True)

    def _std_headers(self) -> dict:
        return {
            "User-Agent":     self._ua,
            "Content-Type":   "application/x-www-form-urlencoded",
            "Accept":         "*/*",
            "X-IG-App-ID":    "936619743392459",
            "X-ASBD-ID":      "198387",
            "X-IG-WWW-Claim": "0",
            "Cookie":         f"sessionid={self.session_id}",
        }

    def _bloks_headers(self, bloks_version: str = None) -> dict:
        bearer = "IGT:2:" + base64.b64encode(
            json.dumps({"ds_user_id": str(self.user_id),
                        "sessionid":  self.session_id}).encode()
        ).decode()
        return {
            "authorization":         f"Bearer {bearer}",
            "user-agent":            "Instagram 390.0.0.43.81 Android (30/11; 420dpi; 1080x2198; samsung; SM-A705FN; a70q; qcom; ar_AE; 766920165)",
            "content-type":          "application/x-www-form-urlencoded; charset=UTF-8",
            "x-ig-app-id":           "567067343352427",
            "x-bloks-version-id":    bloks_version or self.BLOKS_VER,
            "x-bloks-is-layout-rtl": "true",
            "ig-intended-user-id":   str(self.user_id),
            "ig-u-ds-user-id":       str(self.user_id),
            "accept-language":       "ar-AE, en-US",
            "x-ig-device-id":        self._device_id,
            "x-ig-capabilities":     "3brTv10=",
            "accept-encoding":       "gzip, deflate",
        }

    def _get(self, url: str, params=None):
        for attempt in range(5):
            try:
                r = self._sess.get(url, headers=self._std_headers(),
                                   params=params, timeout=30)
                if r.status_code == 429:
                    _backoff(attempt)
                    continue
                return r
            except requests.RequestException:
                time.sleep(5)
        return None

    def _post(self, url: str, data=None):
        for attempt in range(5):
            try:
                r = self._sess.post(url, headers=self._std_headers(),
                                    data=data, timeout=30)
                if r.status_code == 429:
                    _backoff(attempt)
                    continue
                return r
            except requests.RequestException:
                time.sleep(5)
        return None

    def _dismiss_challenge(self):
        try:
            r = requests.post(
                "https://www.instagram.com/api/v1/bloks/apps/"
                "com.instagram.challenge.navigation.take_challenge/",
                headers={
                    "User-Agent":   "Mozilla/5.0",
                    "x-ig-app-id":  "936619743392459",
                    "content-type": "application/x-www-form-urlencoded",
                },
                cookies={"sessionid": self.session_id},
                data={"has_follow_up_screens": "false",
                      "nest_data_manifest":    "true"},
                timeout=15,
                stream=True,
            )
            r.close()
        except Exception:
            pass

    def login(self) -> bool:
        if self.user_id:
            return True
        r = self._get("https://i.instagram.com/api/v1/accounts/current_user/")
        if r is None:
            return False
        try:
            data = r.json()
        except Exception:
            return False
        user = data.get("user") if isinstance(data, dict) else None
        if user:
            self.user_id  = user.get("pk")
            self.username = user.get("username")
            return bool(self.user_id)
        if "automated" in r.text.lower():
            self._dismiss_challenge()
            time.sleep(5)
            return self.login()
        return False

    def _unlike_one(self, media_id: str, media_type: str) -> bool:
        if random.random() < 0.05:
            self._ua = _generate_ua()
        r = self._post(f"https://i.instagram.com/api/v1/media/{media_id}/unlike/")
        if r is None:
            return False
        if r.status_code in (403, 404):
            self._dismiss_challenge()
            _jitter(5, 12)
            r = self._post(f"https://i.instagram.com/api/v1/media/{media_id}/unlike/")
            if r is None or r.status_code != 200:
                return False
        if r.status_code == 200:
            self.total_unliked += 1
            if media_type == "2":
                self.reels_unliked += 1
            else:
                self.posts_unliked += 1
            return True
        return False

    def _process_feed(self, url: str, default_type: str) -> int:
        count  = 0
        max_id = None
        while True:
            r = self._get(url, params={"max_id": max_id} if max_id else {})
            if r is None:
                break
            try:
                data = r.json()
            except Exception:
                break
            items = data.get("items", [])
            if not items:
                break
            for item in items:
                mid   = item.get("id") or item.get("media", {}).get("id")
                mtype = str(item.get("media_type") or
                            item.get("media", {}).get("media_type", default_type))
                if mid and self._unlike_one(mid, mtype):
                    count += 1
                    if self.total_unliked % 5 == 0:
                        self._progress("Likes removed", self.total_unliked)
                _jitter(3.0, 7.0)
            max_id = data.get("next_max_id")
            if not max_id:
                break
            _jitter(5.0, 12.0)
        return count

    def _fetch_reposts(self) -> list:
        body = (f"_uuid={self._device_id}"
                f'&bk_client_context={{"bloks_version":"{self.BLOKS_VER}",'
                f'"styles_id":"instagram"}}'
                f"&bloks_versioning_id={self.BLOKS_VER}")
        try:
            r = self._sess.post(
                "https://i.instagram.com/api/v1/bloks/apps/"
                "com.instagram.privacy.activity_center.media_repost_screen/",
                data=body, headers=self._bloks_headers(), timeout=30,
            )
        except Exception:
            return []
        if r.status_code != 200:
            return []
        raw = r.text
        ids = re.findall(r"\b(\d{15,20}_\d{8,15})\b", raw)
        if not ids:
            for ck in re.findall(r"ig_cache_key=([A-Za-z0-9%+/]+=*)", raw):
                try:
                    dec = base64.b64decode(unquote(ck).split(".")[0]).decode()
                    if dec.isdigit() and 15 <= len(dec) <= 20:
                        ids.append(dec)
                except Exception:
                    pass
        return list(dict.fromkeys(ids))

    def _delete_reposts(self, media_ids: list) -> bool:
        items_str = ",".join(media_ids)
        bk_ctx    = quote(json.dumps({"bloks_version": self.BLOKS_VER,
                                      "styles_id":     "instagram"}))
        body = "&".join([
            f"_uuid={self._device_id}",
            f"bk_client_context={bk_ctx}",
            f"bloks_versioning_id={self.BLOKS_VER}",
            "content_container_id=1151286518",
            "content_element_id=1151286519",
            "content_spinner_id=1151286520",
            "main_order_state_value=true",
            "main_attribute_order_state_value=newest_to_oldest",
            "main_date_start_state_value=-1",
            "main_date_end_state_value=-1",
            "main_authors_state_value=",
            "main_filter_to_visible_on_facebook_value=false",
            "main_includes_location_value=false",
            "main_liked_privately_value=false",
            "main_content_type_value=0",
            "main_content_types_value=Posts%2C+Reels",
            "main_account_history_events_state_value=",
            "main_filter_to_visible_from_facebook_value=false",
            "entrypoint=",
            "shared_user_id=",
            f"number_of_items={len(media_ids)}",
            f"items_for_action={quote(items_str)}",
        ])
        for attempt in range(3):
            try:
                r = self._sess.post(
                    "https://i.instagram.com/api/v1/bloks/apps/"
                    "com.instagram.privacy.activity_center.media_repost_delete/",
                    data=body, headers=self._bloks_headers(), timeout=30,
                )
                if r.status_code == 429:
                    _backoff(attempt)
                    continue
                if r.status_code == 200:
                    self.total_unreposted += len(media_ids)
                    return True
                return False
            except Exception:
                time.sleep(5)
        return False

    def run_unlike(self):
        self._report("Removing likes...")
        while True:
            posts = self._process_feed("https://i.instagram.com/api/v1/feed/liked/", "1")
            reels = self._process_feed("https://i.instagram.com/api/v1/clips/liked/", "2")
            if posts + reels == 0:
                break
            _jitter(8.0, 15.0)
        print()

    def run_unrepost(self):
        self._report("Removing reposts...")
        while True:
            ids = self._fetch_reposts()
            if not ids:
                break
            if not self._delete_reposts(ids):
                removed = 0
                for mid in ids:
                    if self._delete_reposts([mid]):
                        removed += 1
                        self._progress("Reposts removed", self.total_unreposted)
                    _jitter(3.0, 7.0)
                if removed == 0:
                    break
            else:
                self._progress("Reposts removed", self.total_unreposted)
            _jitter(5.0, 10.0)
        print()

    def _bulk_unsave(self, media_ids: list) -> bool:
        body = (f"module_name=feed_saved_collections&_uuid={self._device_id}"
                f"&media_ids={quote(json.dumps(media_ids, separators=(',', ':')))}")
        for attempt in range(3):
            try:
                r = self._sess.post(
                    "https://i.instagram.com/api/v1/collections/bulk_remove/",
                    data=body, headers=self._bloks_headers(self.COMMENTS_BLOKS_VER), timeout=30,
                )
                if r.status_code == 429:
                    _backoff(attempt)
                    continue
                if r.status_code == 200:
                    try:
                        ok = r.json().get("status") == "ok"
                    except Exception:
                        ok = False
                    if ok:
                        self.total_unsaved += len(media_ids)
                    return ok
                return False
            except Exception:
                time.sleep(5)
        return False

    def run_unsave(self):
        self._report("Removing saved posts...")
        max_id = None
        while True:
            url = "https://i.instagram.com/api/v1/feed/saved/posts/?count=12&include_feed_only=false"
            if max_id:
                url += f"&max_id={max_id}"
            try:
                r = self._sess.get(url, headers=self._bloks_headers(self.COMMENTS_BLOKS_VER), timeout=30)
            except Exception:
                break
            if r.status_code != 200:
                break
            try:
                data = r.json()
            except Exception:
                break
            items = data.get("items", [])
            if not items:
                break
            media_ids = []
            for item in items:
                media = item.get("media") or item
                mid = media.get("pk") or media.get("id")
                if mid:
                    media_ids.append(str(mid))
            if media_ids and self._bulk_unsave(media_ids):
                self._progress("Saved posts removed", self.total_unsaved)
            next_max_id = data.get("next_max_id")
            if not next_max_id:
                break
            max_id = next_max_id
            _jitter(5.0, 12.0)
        print()

    def _fetch_comments(self) -> list:
        body = (f"_uuid={self._device_id}"
                f'&bk_client_context={{"bloks_version":"{self.COMMENTS_BLOKS_VER}",'
                f'"styles_id":"instagram","theme_params":[{{"value":["three_neutral_gray"],'
                f'"design_system_name":"XMDS"}}]}}'
                f"&bloks_versioning_id={self.COMMENTS_BLOKS_VER}")
        try:
            r = self._sess.post(
                "https://i.instagram.com/api/v1/bloks/apps/"
                "com.instagram.privacy.activity_center.comments_screen/",
                data=body, headers=self._bloks_headers(self.COMMENTS_BLOKS_VER), timeout=30,
            )
        except Exception:
            return []
        if r.status_code != 200:
            return []
        raw = r.text
        pattern = r'\\"(\d{15,20})\\",\s*\\"(\d{15,20})\\",\s*\\"[A-Za-z0-9_-]+\\",\s*\(dqp'
        pairs, seen = [], set()
        for post_id, comment_id in re.findall(pattern, raw):
            key = (post_id, comment_id)
            if key not in seen:
                seen.add(key)
                pairs.append(key)
        return pairs

    def _delete_comments(self, pairs: list) -> bool:
        items_str = ",".join(f"{post_id}:{comment_id}" for post_id, comment_id in pairs)
        bk_ctx    = quote(json.dumps({"bloks_version": self.COMMENTS_BLOKS_VER,
                                      "styles_id":     "instagram",
                                      "theme_params":  [{"value": ["three_neutral_gray"],
                                                          "design_system_name": "XMDS"}]},
                                     separators=(",", ":")))
        body = "&".join([
            "main_filter_to_visible_on_facebook_value=0",
            "entrypoint=",
            "main_date_end_state_value=-1",
            f"number_of_items={len(pairs)}",
            "content_spinner_id=95067305",
            "content_container_id=95067303",
            "main_attribute_order_state_value=newest_to_oldest",
            f"items_for_action={quote(items_str)}",
            "main_authors_state_value=",
            "main_date_start_state_value=-1",
            f"_uuid={self._device_id}",
            "content_element_id=95067304",
            "main_account_history_events_state_value=",
            "main_content_types_value=Posts%2C+Reels",
            f"bk_client_context={bk_ctx}",
            "main_content_type_value=0",
            "shared_user_id=",
            f"bloks_versioning_id={self.COMMENTS_BLOKS_VER}",
            "main_filter_to_visible_from_facebook_value=0",
            "main_order_state_value=1",
            "main_liked_privately_value=0",
            "main_includes_location_value=0",
        ])
        for attempt in range(3):
            try:
                r = self._sess.post(
                    "https://i.instagram.com/api/v1/bloks/apps/"
                    "com.instagram.privacy.activity_center.comments_delete/",
                    data=body, headers=self._bloks_headers(self.COMMENTS_BLOKS_VER), timeout=30,
                )
                if r.status_code == 429:
                    _backoff(attempt)
                    continue
                if r.status_code == 200:
                    try:
                        ok = r.json().get("status") == "ok"
                    except Exception:
                        ok = False
                    if ok:
                        self.total_comments_deleted += len(pairs)
                    return ok
                return False
            except Exception:
                time.sleep(5)
        return False

    def run_remove_comments(self):
        self._report("Removing comments...")
        while True:
            pairs = self._fetch_comments()
            if not pairs:
                break
            if not self._delete_comments(pairs):
                removed = 0
                for pair in pairs:
                    if self._delete_comments([pair]):
                        removed += 1
                        self._progress("Comments deleted", self.total_comments_deleted)
                    _jitter(3.0, 7.0)
                if removed == 0:
                    break
            else:
                self._progress("Comments deleted", self.total_comments_deleted)
            _jitter(5.0, 10.0)
        print()


def main():
    print("=" * 55)
    print("  Cleaner Tool")
    print("=" * 55)
    session_id = input("\nSession ID: ").strip()
    print("\n[1] Remove Likes\n[2] Remove Reposts\n[3] Remove Saved Posts"
          "\n[4] Remove Comments\n[5] All of the above")
    raw = input("Choose (e.g. 1 or 1,3): ").strip()

    actions = {
        "1": ("Likes",    "run_unlike"),
        "2": ("Reposts",  "run_unrepost"),
        "3": ("Saved",    "run_unsave"),
        "4": ("Comments", "run_remove_comments"),
    }
    picks = list(actions) if raw == "5" else \
        [p.strip() for p in raw.split(",") if p.strip() in actions]
    if not picks:
        print("Invalid choice.")
        return

    tool = CleanerTool(session_id)
    if not tool.login():
        print("Failed to fetch account info.")
        return
    print(f"Logged in as @{tool.username}")

    try:
        for key in picks:
            getattr(tool, actions[key][1])()
        prefix = "Done!"
    except KeyboardInterrupt:
        prefix = "Stopped."

    print(f"\n{prefix}")
    if "1" in picks:
        print(f"Likes removed: {tool.total_unliked}  (Posts: {tool.posts_unliked}  Reels: {tool.reels_unliked})")
    if "2" in picks:
        print(f"Reposts removed: {tool.total_unreposted}")
    if "3" in picks:
        print(f"Saved posts removed: {tool.total_unsaved}")
    if "4" in picks:
        print(f"Comments deleted: {tool.total_comments_deleted}")


if __name__ == "__main__":
    main()
