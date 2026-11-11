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
    "Quyidagi usullardan birini yuboring:\n"
    "• Kanal username yoki havolasi: <code>@uzbekistan</code> yoki <code>https://t.me/uzbekistan</code>\n"
    "• Yopiq kanaldan biror postni shu yerga <b>forward</b> qiling\n"
    "• Yoki qo'lda kiriting:\n"
    "<code>-1001234567890 | Kanal Nomi | https://t.me/+havola</code>\n\n"
    "<i>⚠️ Muhim: Bot o'sha kanalda administrator qilingan bo'lishi shart!</i>\n"
    "<i>Bekor qilish: /cancel</i>"
)
CHANNEL_ADDED_SUCCESS = "✅ Kanal muvaffaqiyatli qo'shildi!\nNomi: <b>{title}</b>\nID: <code>{channel_id}</code>\nHavola: {url}"
CHANNEL_ADD_FAILED = "❌ Kanalni qo'shib bo'lmadi.\nKanal mavjudligini va bot u yerda admin ekanligini tekshiring.\n\n<i>Qayta urinib ko'ring yoki /cancel bosing.</i>"
CHANNEL_ADD_NOT_ADMIN = (
    "❌ <b>Bot ushbu kanalda administrator emas!</b>\n\n"
    "Majburiy obunani tekshirish uchun avval botni kanalga <b>Admin</b> qiling, so'ngra qayta yuboring.\n\n"
    "<i>Bekor qilish: /cancel</i>"
)
CHANNEL_ADD_INVITE_LINK_ONLY = (
    "❌ Taklif havolasi (<code>t.me/+...</code>) orqali kanal ID sini aniqlab bo'lmaydi.\n\n"
    "Kanaldan biror postni shu yerga <b>forward</b> qiling yoki quyidagicha yuboring:\n"
    "<code>-100kanal_id | Kanal Nomi | {invite_url}</code>\n\n"
    "<i>Bekor qilish: /cancel</i>"
)
CHANNEL_ADD_NO_INVITE_LINK = (
    "❌ Yopiq kanal uchun taklif havolasini olib bo'lmadi.\n\n"
    "Botga <b>Foydalanuvchilarni havola orqali taklif qilish</b> huquqini bering yoki havolani qo'lda yuboring:\n"
    "<code>{channel_id} | {title} | https://t.me/+havola</code>\n\n"
    "<i>Bekor qilish: /cancel</i>"
)
CHANNEL_ADD_INVALID_URL = (
    "❌ Kanal havolasi noto'g'ri.\n"
    "Havola <code>https://t.me/...</code> ko'rinishida bo'lishi kerak.\n\n"
    "<i>Qayta urinib ko'ring yoki /cancel bosing.</i>"
)
CHANNEL_ADD_NOT_CHANNEL = "❌ Bu kanal yoki guruh emas. Iltimos, kanal kiriting yoki kanaldan post forward qiling."
CHANNEL_DELETED_SUCCESS = "✅ Homiy kanal o'chirildi: <code>{channel_id}</code>"
CHANNEL_INVALID_URL_ALERT = "⚠️ Kanal havolasi noto'g'ri saqlangan. Uni o'chirib qayta qo'shing."
