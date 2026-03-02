# Uzbek UI Strings for the Media Downloader Bot

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
    "✅ Men eng yaxshi sifatni avtomatik tanlayman!"
)

HELP = (
    "📖 <b>Yordam</b>\n\n"
    "🔗 <b>Qo'llab-quvvatlanadigan platformalar:</b>\n"
    "• YouTube — videolar, shorts, audio\n"
    "• Instagram — postlar, reels\n\n"
    "📝 <b>Buyruqlar:</b>\n"
    "/start — Botni boshlash\n"
    "/help — Yordam ko'rsatish\n\n"
    "💡 <b>Maslahatlar:</b>\n"
    "• Bir xabarda bir nechta havola yuborishingiz mumkin\n"
    "• Havola yuborganingizda 🎬 Video va 🎧 Audio tugmalari paydo bo'ladi\n"
    "• Bot avtomatik ravishda eng yaxshi sifatni tanlaydi\n"
    "• 50 MB dan katta fayllar avtomatik siqiladi\n\n"
    "🎧 <b>Videodan musiqa ajratish:</b>\n"
    "Menga istalgan video faylni yuboring va men undan\n"
    "audioni MP3 formatida ajratib beraman!"
)

# Inline button flow
FETCHING_INFO = "🔍 Ma'lumotlar olinmoqda..."
CHOOSE_FORMAT = "Yuklab olish formatlari ↓"
DOWNLOADING_VIDEO = "⏳ Video yuklanmoqda..."
DOWNLOADING_AUDIO = "⏳ Audio yuklanmoqda..."

# Audio extraction
AUDIO_EXTRACTING = "🎧 Videodan audio ajratilmoqda..."
AUDIO_EXTRACT_SUCCESS = "🎵 <b>{title}</b>\n📦 {size}"
AUDIO_EXTRACT_NO_VIDEO = "⚠️ Iltimos, menga video fayl yuboring. Men undan audioni ajratib beraman."
AUDIO_EXTRACT_TOO_LARGE = "❌ Video fayl juda katta. Iltimos, 50 MB dan kichik video yuboring."

# Errors
ERROR_GENERIC = "❌ Xatolik yuz berdi. Iltimos, qayta urinib ko'ring."
ERROR_INVALID_URL = "⚠️ Noto'g'ri havola. Iltimos, YouTube yoki Instagram havolasini yuboring."
ERROR_DOWNLOAD_FAILED = "❌ Yuklab olishda xatolik. Havola to'g'ri ekanligini tekshiring."
ERROR_FILE_TOO_LARGE = "❌ Fayl juda katta (siqishdan keyin ham 50 MB dan oshadi)."
ERROR_INSTAGRAM_PRIVATE = "🔒 Bu Instagram akkaunt yopiq. Yopiq kontentni yuklab bo'lmaydi."
ERROR_INSTAGRAM_STORY = "📛 Instagram story'larni yuklab bo'lmaydi — ular faqat tizimga kirgan foydalanuvchilarga ko'rinadi."
ERROR_NOT_FOUND = "🔍 Media topilmadi. Havola hali ham amal qilishini tekshiring."
ERROR_RATE_LIMIT = "⏱ Juda ko'p so'rov. Iltimos, bir oz kuting va qayta urinib ko'ring."
ERROR_FFMPEG_MISSING = "⚠️ Audio ajratish xizmati vaqtinchalik ishlamayapti. Iltimos, keyinroq urinib ko'ring."
ERROR_LINK_EXPIRED = "⏱ Havola muddati tugadi. Iltimos, havolani qayta yuboring."

# Admin messages
ADMIN_BOT_STARTED = "🤖 Bot ishga tushdi!"
ADMIN_ERROR_REPORT = "🚨 <b>Xatolik:</b>\nFoydalanuvchi: {user_id}\nHavola: {url}\nXato: {error}"
