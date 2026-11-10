"""User-facing strings in Uzbek."""

START_WELCOME = (
    "👋 <b>Salom! Men ClipGrab botiman.</b>\n\n"
    "📥 <b>Video linkini yuboring:</b>"
)

HELP_MESSAGE = (
    "ℹ️ <b>Yordam va ma'lumot</b>\n\n"
    "<b>Qo'llab-quvvatlanadigan platformalar:</b>\n"
    "• YouTube (Shorts va videolar)\n"
    "• TikTok\n"
    "• Instagram (Reels, postlar)\n"
    "• Facebook\n"
    "• X (Twitter)\n"
    "• Pinterest\n\n"
    "<b>Cheklovlar:</b>\n"
    "• Maksimal hajm: 50 MB\n"
    "• Maksimal davomiylik: 10 daqiqa\n\n"
    "<i>Video linkini yuboring, qolganini o'zim bajaramiz!</i>"
)

STATUS_DOWNLOADING = "⏳ Yuklanmoqda..."

ERR_ALREADY_DOWNLOADING = "Avvalgi video yuklanyapti, biroz kuting 🙂"
ERR_NOT_ALLOWED = "Bu sayt qo'llab-quvvatlanmaydi."
ERR_PRIVATE_OR_LOGIN = "Bu video yopiq yoki login talab qiladi."
ERR_TOO_LARGE = "Video 50 MB dan katta, yubora olmayman."
ERR_TOO_LONG = "Video juda uzun."
ERR_TIMEOUT = "Yuklash juda uzoq davom etdi, keyinroq urinib ko'ring."
ERR_GENERAL = "Yuklab bo'lmadi. Link ochiq ekanini tekshiring."

# Mandatory subscription texts
SUB_REQUIRED = "⚠️ <b>Botdan foydalanish uchun quyidagi homiy kanal(lar)ga obuna bo'ling:</b>"
SUB_CHECK_SUCCESS = "✅ <b>Obuna tasdiqlandi!</b>\n\n📥 <b>Video linkini yuboring:</b>"
SUB_CHECK_FAIL = "❌ Siz hali barcha kanallarga obuna bo'lmadingiz! Iltimos, a'zo bo'lib, qayta tekshiring."

# Admin Panel texts
ADMIN_ONLY = "Kechirasiz, bu buyruq faqat bot adminlari uchun."
ADMIN_PANEL_TITLE = "⚙️ <b>Admin Boshqaruv Paneli</b>\n\nKerakli bo'limni tanlang:"
ADMIN_BTN_STATS = "📊 Statistika"
ADMIN_BTN_BROADCAST = "📢 Reklama tarqatish"
ADMIN_BTN_CHANNELS = "📢 Homiy kanallar"
ADMIN_BTN_UPDATE_YTDLP = "🔄 yt-dlp yangilash"
ADMIN_BTN_BACK = "◀️ Orqaga"
ADMIN_BTN_ADD_CHANNEL = "➕ Yangi kanal qo'shish"

ADMIN_UPDATE_STARTED = "🔄 yt-dlp yangilanmoqda, kuting..."
ADMIN_UPDATE_SUCCESS = "✅ yt-dlp muvaffaqiyatli yangilandi!\nJoriy versiya: <code>{version}</code>"
ADMIN_UPDATE_FAILED = "❌ Yangilashda xatolik yuz berdi:\n<code>{error}</code>"

STATS_TEMPLATE = (
    "📊 <b>Bot statistikasi (oxirgi 24 soat):</b>\n\n"
    "👥 Jami foydalanuvchilar: <b>{total_users}</b>\n"
    "📢 Homiy kanallar soni: <b>{total_channels}</b>\n"
    "📥 Jami yuklash so'rovlari: <b>{total_downloads}</b>\n"
    "⚡ Keshdan yuborilgan: <b>{cache_hits}</b> ({hit_rate:.1f}%)\n"
    "❌ Xatoliklar soni: <b>{failures}</b>"
)

# Broadcast texts
BROADCAST_START_PROMPT = (
    "📢 <b>Foydalanuvchilarga reklama yuborish</b>\n\n"
    "Barcha a'zolarga jo'natmoqchi bo'lgan xabaringizni (matn, rasm, video, audio yoki forward) yuboring.\n\n"
    "<i>Bekor qilish: /cancel</i>"
)
BROADCAST_PROGRESS = "⏳ Reklama tarqatilmoqda... Iltimos, kuting."
BROADCAST_FINISHED = (
    "✅ <b>Reklama muvaffaqiyatli tarqatildi!</b>\n\n"
    "🎯 Jami foydalanuvchilar: <b>{total}</b>\n"
    "📨 Yetib bordi: <b>{sent}</b>\n"
    "🚫 Bloklaganlar: <b>{blocked}</b>"
)
BROADCAST_CANCELLED = "❌ Reklama yuborish bekor qilindi."

# Channels management texts
CHANNELS_EMPTY = "📢 Hozirda hech qanday homiy kanal qo'shilmagan."
CHANNELS_TITLE = "📢 <b>Faol homiy kanallar ro'yxati:</b>\n\n<i>Kanalni o'chirish uchun uning yonidagi ❌ tugmasini bosing:</i>"
CHANNEL_ADD_PROMPT = (
    "➕ <b>Yangi homiy kanal qo'shish:</b>\n\n"
    "Kanal ma'lumotlarini bitta xabarda quyidagi tartibda yuboring:\n"
    "<code>@kanal_usernomi | Kanal Nomi | https://t.me/havola</code>\n\n"
    "Yoki faqat kanal usernamesini yuboring (masalan: <code>@uzbekistan</code>)\n\n"
    "<i>⚠️ Muhim: Bot o'sha kanalda administrator qilingan bo'lishi shart!</i>\n"
    "<i>Bekor qilish: /cancel</i>"
)
CHANNEL_ADDED_SUCCESS = "✅ Kanal muvaffaqiyatli qo'shildi!\nNomi: <b>{title}</b>\nID/User: <code>{channel_id}</code>\nHavola: {url}"
CHANNEL_ADD_FAILED = "❌ Kanalni qo'shib bo'lmadi.\nKanal mavjudligini va bot u yerda admin ekanligini tekshiring."
CHANNEL_DELETED_SUCCESS = "✅ Homiy kanal o'chirildi: <code>{channel_id}</code>"
