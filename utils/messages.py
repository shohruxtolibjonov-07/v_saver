# ─────────────────────────────────────────────────
# O'zbek tilidagi UI Stringlar — Media Yuklovchi Bot
# ─────────────────────────────────────────────────

WELCOME = (
    "🎬 <b>Media Yuklovchi Botga Xush Kelibsiz!</b>\n\n"
    "Men Instagram va YouTube'dan media fayllarni yuklab beraman.\n\n"
    "📌 <b>Qanday foydalanish:</b>\n"
    "Menga shunchaki havola (link) yuboring:\n\n"
    "▶️ YouTube video yoki Shorts\n"
    "📸 Instagram post, reel\n\n"
    "🎬 Video yoki 🎧 Audio formatni tanlash tugmalari paydo bo'ladi!\n\n"
    "🎧 <b>Videodan musiqa ajratish:</b>\n"
    "Menga istalgan video faylni yuboring — men undan audioni ajratib beraman!\n\n"
    "✅ Men eng yaxshi sifatni avtomatik tanlayman!\n\n"
    "⚖️ /terms — Foydalanish shartlari"
)

HELP = (
    "📖 <b>Yordam</b>\n\n"
    "🔗 <b>Qo'llab-quvvatlanadigan platformalar:</b>\n"
    "• YouTube — videolar, shorts, audio\n"
    "• Instagram — postlar, reels\n\n"
    "📝 <b>Buyruqlar:</b>\n"
    "/start — Botni boshlash\n"
    "/help — Yordam ko'rsatish\n"
    "/terms — Foydalanish shartlari\n"
    "/report — Mualliflik huquqi buzilishi haqida xabar berish\n\n"
    "💡 <b>Maslahatlar:</b>\n"
    "• Bir xabarda bir nechta havola yuborishingiz mumkin\n"
    "• Havola yuborganingizda 🎬 Video va 🎧 Audio tugmalari paydo bo'ladi\n"
    "• Bot avtomatik ravishda eng yaxshi sifatni tanlaydi\n"
    "• Katta fayllar (>50 MB) uchun sifat tanlash imkoniyati beriladi\n\n"
    "• Bot avtomatik ravishda eng yaxshi sifatni tanlaydi\n\n"
    "🎧 <b>Videodan musiqa ajratish:</b>\n"
    "Menga istalgan video faylni yuboring va men undan\n"
    "audioni MP3 formatida ajratib beraman!"
)

TERMS_OF_SERVICE = (
    "⚖️ <b>Foydalanish Shartlari</b>\n\n"
    "Bu bot faqat quyidagi kontentni yuklab olish uchun mo'ljallangan:\n\n"
    "✅ Ommaviy (public domain) kontent\n"
    "✅ Foydalanuvchining o'ziga tegishli kontent\n"
    "✅ Muallif/platforma tomonidan yuklab olishga ruxsat berilgan kontent\n\n"
    "❌ Mualliflik huquqi bilan himoyalangan kontentni ruxsatsiz yuklab olish <b>taqiqlanadi</b>.\n\n"
    "⚠️ <b>Javobgarlik:</b>\n"
    "Foydalanuvchi yuklab olgan kontent uchun to'liq javobgarlikni o'z zimmasiga oladi. "
    "Bot administratsiyasi mualliflik huquqi buzilishi uchun javobgar emas.\n\n"
    "📢 <b>Shikoyat:</b>\n"
    "Agar sizning kontentingiz ruxsatsiz yuklab olingan bo'lsa, /report buyrug'i orqali "
    "xabar bering. Biz zudlik bilan choralar ko'ramiz.\n\n"
    "🌐 Bot YouTube va Instagram platformalari foydalanish shartlariga rioya qiladi."
)

REPORT_INFO = (
    "📢 <b>Mualliflik huquqi buzilishi haqida xabar berish</b>\n\n"
    "Agar sizning kontentingiz ruxsatsiz yuklab olingan bo'lsa:\n\n"
    "1️⃣ Kontentga havola (link)\n"
    "2️⃣ Sizning mualliflik huquqingizni tasdiqlovchi dalil\n"
    "3️⃣ Bog'lanish uchun ma'lumotlaringiz\n\n"
    "Yuqoridagi ma'lumotlarni shu chatga yozing — admin ko'rib chiqadi."
)

# ─── Inline button flow ─────────────────────────
CHOOSE_FORMAT = "Yuklab olish formatini tanlang ↓"
DOWNLOADING_VIDEO = "⏳ Video yuklanmoqda..."
DOWNLOADING_AUDIO = "⏳ Audio yuklanmoqda..."
CHECKING_INFO = "🔍 Ma'lumotlar tekshirilmoqda..."

# ─── Quality selection (>50 MB) ─────────────────
QUALITY_CHOICE = (
    "📁 <b>Fayl hajmi:</b> {size}\n\n"
    "Fayl katta. Sifatni tanlang:"
)
QUALITY_PROCESSING = "⚙️ {quality} sifatda tayyorlanmoqda..."

# ─── Audio extraction ───────────────────────────
AUDIO_EXTRACTING = "🎧 Videodan audio ajratilmoqda..."
AUDIO_EXTRACT_SUCCESS = "🎵 <b>{title}</b>\n📦 {size}"
AUDIO_EXTRACT_TOO_LARGE = "❌ Video fayl juda katta. Iltimos, 50 MB dan kichik video yuboring."

# ─── Errors ─────────────────────────────────────
ERROR_GENERIC = "❌ Xatolik yuz berdi. Iltimos, qayta urinib ko'ring."
ERROR_INVALID_URL = "⚠️ Noto'g'ri havola. Iltimos, YouTube yoki Instagram havolasini yuboring."
ERROR_DOWNLOAD_FAILED = "❌ Yuklab olishda xatolik. Havola to'g'ri ekanligini tekshiring."
ERROR_FILE_TOO_LARGE = (
    "❌ Fayl juda katta va Telegram orqali yuborib bo'lmaydi.\n"
    "Iltimos, pastroq sifatni tanlang yoki kichikroq video sinab ko'ring."
)
ERROR_FILE_TOO_LARGE = "❌ Fayl juda katta (2 GB dan oshadi). Iltimos, kichikroq fayl yuboring."
ERROR_INSTAGRAM_PRIVATE = "🔒 Bu Instagram akkaunt yopiq. Yopiq kontentni yuklab bo'lmaydi."
ERROR_INSTAGRAM_STORY = "📛 Instagram story'larni yuklab bo'lmaydi — ular faqat tizimga kirgan foydalanuvchilarga ko'rinadi."
ERROR_NOT_FOUND = "🔍 Media topilmadi. Havola hali ham amal qilishini tekshiring."
ERROR_RATE_LIMIT = "⏱ Juda ko'p so'rov. Iltimos, {seconds} soniya kuting va qayta urinib ko'ring."
ERROR_FFMPEG_MISSING = "⚠️ Audio ajratish xizmati vaqtinchalik ishlamayapti. Iltimos, keyinroq urinib ko'ring."
ERROR_LINK_EXPIRED = "⏱ Havola muddati tugadi. Iltimos, havolani qayta yuboring."
ERROR_QUEUE_FULL = "⏳ Hozirda juda ko'p so'rov bor. Iltimos, bir ozdan keyin qayta urinib ko'ring."

# ─── Admin messages ─────────────────────────────
ADMIN_BOT_STARTED = "🤖 Bot ishga tushdi!\n📊 Workers: {workers}\n🗄 Redis: ulangan"
ADMIN_ERROR_REPORT = "🚨 <b>Xatolik:</b>\nFoydalanuvchi: {user_id}\nHavola: {url}\nXato: {error}"
ADMIN_STATS = (
    "📊 <b>Bot Statistikasi</b>\n\n"
    "👥 Jami foydalanuvchilar: {total_users}\n"
    "📥 Jami yuklanmalar: {total_downloads}\n"
    "📋 Navbatdagi joblar: {queue_size}\n"
    "⚙️ Faol workerlar: {active_workers}/{total_workers}\n"
    "⏸ Holat: {status}"
)
ADMIN_BROADCAST_DONE = "📢 Broadcast tugadi!\n✅ Yuborildi: {success}\n❌ Xato: {failed}"
ADMIN_BROADCAST_STARTED = "📢 Broadcast boshlandi... {total} ta foydalanuvchiga yuborilmoqda."
ADMIN_QUEUE_STATUS = (
    "📋 <b>Queue Holati</b>\n\n"
    "📥 Navbatda: {pending}\n"
    "⚙️ Jarayonda: {processing}\n"
    "✅ Bajarildi: {completed}\n"
    "❌ Xatolik: {failed}"
)
ADMIN_ONLY = "⛔ Bu buyruq faqat admin uchun."
ADMIN_PAUSED = "⏸ Worker pool to'xtatildi."
ADMIN_RESUMED = "▶️ Worker pool qayta ishga tushdi."
ADMIN_JOB_CANCELLED = "🗑 Job bekor qilindi: {job_id}"
ADMIN_JOB_NOT_FOUND = "❌ Job topilmadi: {job_id}"

# ─── Caption template ───────────────────────────
CAPTION_VIDEO = "🎬 <b>{title}</b>\n⏱ {duration}\n📦 {size}\n\n@{bot_username}"
CAPTION_AUDIO = "🎧 <b>{title}</b>\n⏱ {duration}\n📦 {size}\n\n@{bot_username}"
CAPTION_DOCUMENT = "📁 <b>{title}</b>\n📦 {size}\n\n@{bot_username}"
CAPTION_INSTAGRAM = "📸 <b>{title}</b>\n📦 {size}\n\n@{bot_username}"
