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
    "• Maksimal davomiylik: 10 daqiqa\n"
    "• 18+ va nomaqbul mazmundagi videolar yuklanmaydi\n\n"
    "<i>Video linkini yuboring, qolganini o'zim bajaramiz!</i>"
)

STATUS_DOWNLOADING = "⏳ Yuklanmoqda..."

ERR_ALREADY_DOWNLOADING = "Avvalgi video yuklanyapti, biroz kuting 🙂"
ERR_NOT_ALLOWED = (
    "ℹ️ Bu havola qo'llab-quvvatlanmaydi.\n\n"
    "Bot YouTube, TikTok, Instagram, Facebook, X (Twitter) va Pinterest dagi videolarni yuklaydi. "
    "Shunday havola yuboring 👇"
)
ERR_PRIVATE_OR_LOGIN = "Bu video yopiq yoki login talab qiladi."
ERR_CONTENT_BLOCKED = "🚫 Bu videoni yuklay olmayman. U bot qoidalariga zid."
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
ADMIN_BTN_PROMO = "📣 Avto-reklama"
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
    "❌ Yuklash xatoliklari: <b>{failures}</b>\n"
    "🔗 Rad etilgan havolalar (qo'llab-quvvatlanmaydigan sayt va h.k.): <b>{rejected}</b>\n"
    "🚫 Qoidaga zid kontent (bloklangan): <b>{blocked}</b>"
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

# Auto-promo texts
AD_RECEIVED = "✅ <b>Reklama qabul qilindi</b> ({kind}).\n\nQayerga yuboramiz?"
AD_BTN_USERS = "👥 Foydalanuvchilarga yuborish"
AD_BTN_CHANNEL = "📣 Kanal/guruhga avto-reklama"
AD_BTN_CANCEL = "❌ Bekor qilish"
PROMO_MENU = (
    "📣 <b>Avto-reklama</b>\n\n"
    "Oxirgi yuborgan reklamangiz (video, rasm yoki matn) tanlangan <b>bitta</b> kanal/guruhga "
    "avtomatik qaytarib turiladi.\n\n"
    "Holat: <b>{status}</b>\n"
    "🎯 Chat: <b>{chat}</b>\n"
    "⏱ Har: <b>{interval}</b> da\n"
    "⏳ Davomiyligi: <b>{duration}</b>{remaining}\n"
    "🎬 Reklama: <b>{ad}</b>\n\n"
    "{error_line}"
    "<i>Yoqilganda birinchi reklama darhol chiqadi, keyin tanlangan intervalda takrorlanadi.</i>"
)
PROMO_REMAINING = " (qoldi: {left})"
PROMO_AD_NONE = "hali yo'q (avval «Reklama tarqatish» orqali yuboring)"
PROMO_AD_SAVED = "{kind} (saqlangan)"
PROMO_ERROR_LINE = "⚠️ Oxirgi xatolik: <code>{error}</code>\n\n"
PROMO_BTN_ENABLE = "▶️ Yoqish"
PROMO_BTN_DISABLE = "⏸ O'chirish"
PROMO_BTN_CHAT = "🎯 Chatni tanlash"
PROMO_BTN_INTERVAL = "⏱ Intervalni tanlash"
PROMO_BTN_DURATION = "⏳ Davomiyligini tanlash"
PROMO_BTN_NOW = "📤 Hozir yuborish"
PROMO_NEED_CHAT = "Avval reklama yuboriladigan chatni tanlang."
PROMO_NEED_AD = "Avval «Reklama tarqatish» orqali reklamani yuboring."
PROMO_CHOOSE_CHAT = (
    "🎯 <b>1/3. Reklama yuboriladigan chatni tanlang</b>\n\n"
    "Faqat «Homiy kanallar» ro'yxatidagi, bot admin bo'lgan kanal/guruhlar chiqadi."
)
PROMO_NO_CHANNELS = (
    "📢 Homiy kanallar ro'yxati bo'sh.\n\n"
    "Avval «Homiy kanallar» bo'limida kanal/guruh qo'shing (bot u yerda admin bo'lishi shart)."
)
PROMO_CHOOSE_INTERVAL = "⏱ <b>2/3. Reklama necha vaqtda bir yuborilsin?</b>"
PROMO_CHOOSE_DURATION = "⏳ <b>3/3. Avto-reklama necha soat davom etsin?</b>\n\nBelgilangan vaqt tugagach bot o'zi to'xtaydi."
PROMO_STARTED_TOAST = "✅ Avto-reklama boshlandi"
PROMO_SENT_OK = "✅ Reklama yuborildi."
PROMO_SENT_FAIL = "❌ Yuborib bo'lmadi: {error}"
PROMO_FINISHED = (
    "⏹ <b>Avto-reklama muddati tugadi</b> va to'xtatildi.\n"
    "Chat: <b>{chat}</b>\n\n"
    "Qayta boshlash: /admin → «Avto-reklama»."
)

# Referral (taklif) and video branding texts
VIDEO_BRAND = "📥 @{bot} orqali yuklandi"
SHARE_TEXT = "📥 TikTok, Instagram, YouTube va boshqa videolarni bir zumda yuklab oling!"
REF_BTN_SHARE = "📤 Do'stga ulashish"
REF_BTN_INVITE = "👥 Do'stlarni taklif qilish"
REF_BTN_TOP = "🏆 TOP taklifchilar"
REF_MY_INFO = (
    "👥 <b>Do'stlarni taklif qilish</b>\n\n"
    "Sizning havolangiz:\n<code>{link}</code>\n\n"
    "✅ Tasdiqlangan takliflar: <b>{confirmed}</b>\n"
    "⏳ Kutilayotgan: <b>{pending}</b>\n"
    "🏅 Reytingdagi o'rningiz: <b>{rank}</b>\n\n"
    "<i>Taklif quyidagi hollarda sanaladi: do'stingiz botni <b>birinchi marta</b> ochsa va barcha homiy kanallarga obuna bo'lsa. "
    "Botdan avval foydalangan odamlar va o'zingiz sanalmaydi.</i>"
)
REF_RANK_NONE = "hali yo'q"
REF_NEW_FRIEND = "🎉 Yangi do'stingiz botga qo'shildi!\nTasdiqlangan takliflaringiz: <b>{count}</b>"
REF_TOP_TITLE = "🏆 <b>TOP taklifchilar</b>\n\n{rows}"
REF_TOP_ROW = "{medal} {name} — <b>{count}</b>"
REF_TOP_EMPTY = "Hozircha hech kim do'st taklif qilmagan. Birinchi bo'ling! 🚀"
REF_TOP_YOU = "\n\nSizning o'rningiz: <b>{rank}</b> ({count} ta taklif)"
REF_TOP_YOU_NONE = "\n\nSiz hali hech kimni taklif qilmagansiz. «Do'stlarni taklif qilish» tugmasini bosing."
REF_ANON_NAME = "Foydalanuvchi …{tail}"

# Referral contest
ADMIN_BTN_CONTEST = "🎁 Konkurs"
CONTEST_PRIZE = "1 oylik Telegram Premium"
CT_BTN_OPEN = "🎁 Konkurs"
CT_BTN_JOIN = "🎁 Qatnashish"
CT_BTN_TOP = "🏆 Konkurs reytingi"
CT_NONE = "🎁 Hozircha faol konkurs yo'q.\n\nYangi konkurs boshlanganda xabar beramiz!"
CT_RULES = (
    "🎁 <b>KONKURS: {prize}</b>\n"
    "<b>{winners} ta g'olib</b> har biri {prize} oladi!\n\n"
    "<b>Qanday qatnashiladi?</b>\n"
    "1️⃣ «🎁 Qatnashish» tugmasini bosing.\n"
    "2️⃣ Botdan biror video yuklab oling: havolani shu yerga yuboring (video yuklamasangiz shart bajarilmaydi).\n"
    "3️⃣ Videoning tagidagi «📤 Do'stga ulashish» tugmasi orqali yoki o'z havolangizni yuborib, do'stlaringizni taklif qiling.\n"
    "4️⃣ Kamida <b>{min} ta do'stingiz</b> sizning havolangiz orqali botga kirsa, shart bajariladi.\n\n"
    "<b>Do'st qachon sanaladi?</b>\n"
    "✅ Botga <b>birinchi marta</b> kirib, /start bosganda\n"
    "✅ Homiy kanallarga obuna bo'lganda (obuna bo'lmaguncha sanalmaydi)\n"
    "❌ Botdan oldin foydalangan odam sanalmaydi\n"
    "❌ O'zingizni o'zingiz taklif qilsangiz sanalmaydi\n"
    "❌ Konkurs boshlanishidan oldingi takliflar sanalmaydi\n\n"
    "<b>G'oliblar qanday aniqlanadi?</b>\n"
    "🥇 1-o'rin: eng ko'p do'st taklif qilgan odam\n"
    "🎲 Qolgan o'rinlar: shartni bajarganlar orasidan tasodifiy tanlanadi\n"
    "Natijani admin tekshiradi. Soxta akkauntlar orqali olingan takliflar hisobga olinmaydi, "
    "qoidani buzgan odam konkursdan chetlatiladi.\n\n"
    "⏳ Konkursga <b>{left}</b> qoldi.\n"
    "📅 <b>{last}</b> kuni soat 23:59 gacha (Toshkent vaqti) qatnashish mumkin, g'oliblar shundan keyin aniqlanadi.\n"
    "Natija chiqqach g'oliblarga shu bot orqali xabar beriladi."
)
CT_MEMBER_INFO = (
    "\n\n✅ <b>Siz konkursdasiz!</b>\n"
    "👥 Tasdiqlangan takliflaringiz: <b>{count}</b> / {min}\n"
    "📊 Reytingdagi o'rningiz: <b>{rank}</b>{pending_line}{dl_line}\n\n"
    "Sizning havolangiz:\n<code>{link}</code>"
)
CT_PENDING_LINE = (
    "\n⏳ Kutilayotgan do'stlar: <b>{count}</b> (ular homiy kanallarga obuna bo'lgach sanaladi)"
)
CT_NEED_DOWNLOAD = "\n⚠️ Shart: botdan kamida bitta video yuklab oling."
CT_DISQUALIFIED = "\n\n🚫 Siz konkursdan chetlatilgansiz."
CT_JOINED_TOAST = "✅ Siz konkursga qo'shildingiz!"
CT_ALREADY_TOAST = "Siz allaqachon qatnashyapsiz"
CT_NOT_ACTIVE_TOAST = "Konkurs hozir faol emas"
CT_PRIVATE_ONLY_TOAST = "Qatnashish uchun botga shaxsiy chatda kiring"
CT_TOP_TITLE = "🏆 <b>Konkurs reytingi</b>\n\n{rows}"
CT_TOP_ROW = "{medal} {name} — <b>{count}</b>"
CT_TOP_EMPTY = "Hozircha qatnashuvchilar yo'q. Birinchi bo'ling! 🚀"
CT_DAYS_LEFT = "{days} kun {hours} soat"
CT_HOURS_LEFT = "{hours} soat {minutes} daqiqa"

CT_ADMIN_MENU = (
    "🎁 <b>Konkurs</b>\n\n"
    "Holat: {status}\n"
    "Sovg'a: <b>{prize}</b>\n"
    "Shart: kamida <b>{min}</b> ta taklif\n"
    "G'oliblar soni: <b>{winners}</b>\n"
    "Davomiyligi: <b>{days}</b> kun (yangi konkurs boshlanganda so'raladi)\n"
    "Qatnashuvchilar: <b>{members}</b>{extra}"
)
CT_STATUS_OFF = "🔴 O'chiq"
CT_STATUS_RUNNING = "🟢 Davom etmoqda"
CT_STATUS_ENDED = "🏁 Yakunlangan"
CT_EXTRA_LEFT = "\nTugashiga: <b>{left}</b> ({last} gacha)"
CT_EXTRA_QUALIFIED = "\nShartni bajarganlar: <b>{count}</b>"
CT_BTN_START = "▶️ Konkursni boshlash"
CT_BTN_FINISH = "🏁 Hozir yakunlash"
CT_BTN_CANCEL = "🛑 Bekor qilish"
CT_BTN_ADMIN_TOP = "📋 Reyting"
CT_BTN_RESULT = "🏆 Natija"
CT_BTN_NOTIFY = "📢 G'oliblarga xabar yuborish"
CT_BTN_SET_MIN = "✅ Shart: {n} ta"
CT_BTN_SET_DAYS = "⏳ {n} kun"
CT_BTN_SET_WIN = "🥇 G'oliblar: {n}"
CT_PICK_MIN = "✅ <b>Kamida nechta taklif kerak?</b>"
CT_PICK_DAYS = "⏳ <b>Konkurs necha kun davom etsin?</b>"
CT_PICK_WIN = "🥇 <b>Nechta g'olib bo'lsin?</b>"
CT_STARTED_TOAST = "✅ Konkurs boshlandi"
CT_CANCELLED_TOAST = "Konkurs bekor qilindi"
CT_NOT_RUNNING_TOAST = "Konkurs davom etmayapti"
CT_ADMIN_TOP_TITLE = "📋 <b>Konkurs reytingi</b> (✅ — shartni bajargan)\n\n{rows}"
CT_ADMIN_TOP_ROW = "{mark} {rank}. {name} — <b>{count}</b> taklif, {dl} video"
CT_FINISHED_HEAD = "🏁 <b>Konkurs muddati tugadi!</b>\n\n"
CT_RESULT_TITLE = (
    "🏆 <b>Konkurs natijasi</b>\n\n{rows}\n\n"
    "Shubhali (soxta) takliflarni tekshiring: kerak bo'lsa ❌ bilan chetlating, bot o'rniga boshqasini tanlaydi. "
    "Hammasi to'g'ri bo'lsa «G'oliblarga xabar yuborish» tugmasini bosing, so'ng Premium'ni o'zingiz sovg'a qilasiz."
)
CT_RESULT_ROW = "{place}-o'rin: {name} — <b>{count}</b> taklif ({kind}){notified}"
CT_KIND_TOP = "eng ko'p"
CT_KIND_RANDOM = "tasodifiy"
CT_NOTIFIED_MARK = " ✅ xabar yuborilgan"
CT_RESULT_EMPTY = "Shartni bajargan qatnashuvchi bo'lmadi, g'olib yo'q."
CT_BTN_DQ = "❌ Chetlatish: {name}"
CT_NOTIFY_DONE = "📢 {count} ta g'olibga xabar yuborildi."
CT_NOTIFY_NONE = "Xabar yuboriladigan g'olib yo'q (hammasiga yuborilgan yoki bot bloklangan)."
CT_WINNER_MSG = (
    "🎉 <b>Tabriklaymiz!</b>\n\n"
    "Siz konkursda g'olib bo'ldingiz!\n"
    "🎁 Sovg'a: <b>{prize}</b>\n\n"
    "Tez orada admin siz bilan bog'lanadi."
)

CT_BTN_ANNOUNCE = "📣 Hammaga e'lon yuborish"
CT_BTN_ANNOUNCE_YES = "✅ Ha, yuborish"
CT_ANNOUNCE_CONFIRM = (
    "📣 Konkurs e'loni <b>{count}</b> ta foydalanuvchiga yuboriladi.\n"
    "E'lon tagida «Qatnashish» tugmasi bo'ladi: bosgan odam botga o'tadi va bot unga qoidalarni o'zi aytadi.\n\n"
    "Yuborilsinmi?"
)
CT_ANNOUNCE = (
    "🎁 <b>KONKURS! {prize} yutib oling!</b>\n\n"
    "<b>{winners} ta g'olib</b>. Qatnashish oson: pastdagi tugmani bosing, bot qoidalarni o'zi tushuntiradi.\n\n"
    "⏳ Qatnashish muddati: <b>{last}</b> gacha"
)
CT_ANNOUNCE_BTN = "🎁 Konkursda qatnashish"
CT_ANNOUNCE_DONE = "📣 E'lon yuborildi: {sent} ta, yetib bormadi: {blocked} ta.\n\nKanalga qo'yish uchun e'lonni o'zingizga kelgan xabardan forward qiling."
CT_ANNOUNCE_NOT_ACTIVE = "Avval konkursni boshlang."
CT_EXTRA_LINK = "\nKonkurs havolasi (kanal/guruhga qo'yish uchun):\n<code>{link}</code>"

CT_LAST_DAY = "1 kun (bugun oxirgi kun!)"
CT_FEW_HOURS = "bir necha soat"
CT_POST_FOOTER = "\n\n⏳ <b>Konkursga {left} qoldi</b> · {last} gacha"
CT_POST_FOOTER_DONE = "\n\n🏁 <b>{note}</b>"
CT_POST_ENDED = "Konkurs yakunlandi!"
CT_POST_CANCELLED = "Konkurs to'xtatildi."

CT_PICK_START_DAYS = (
    "⏳ <b>1/3. Konkurs necha kun davom etsin?</b>\n\n"
    "Qolgan kunlar soni har kuni tun 00:00 da (Toshkent vaqti) o'zi kamayib boradi."
)
CT_PICK_POST_CHAT = "📢 <b>2/3. E'lon qaysi kanal yoki guruhga yuborilsin?</b>\n\nBot o'sha yerda admin bo'lishi kerak."
CT_NO_POST_CHANNELS = (
    "📢 Kanal yoki guruh topilmadi.\n\n"
    "Avval «Homiy kanallar» bo'limiga kanal/guruh qo'shing (bot u yerda admin bo'lsin)."
)
CT_BTN_NO_POST = "⏭ E'lonsiz boshlash"
CT_ASK_POST_CONTENT = (
    "📝 <b>3/3. E'lon uchun matn, rasm yoki video yuboring.</b>\n\n"
    "Rasm yoki video bo'lsa, matnni izoh sifatida yozing.\n"
    "Bot oxiriga «Konkursga N kun qoldi» qatorini va «Qatnashish» tugmasini o'zi qo'shadi, "
    "kunlar soni har kuni avtomatik yangilanadi.\n\n"
    "Bekor qilish: /cancel"
)
CT_POST_TOO_LONG = "⚠️ Matn juda uzun ({n} belgi). Ko'pi bilan {limit} belgi yozing va qayta yuboring."
CT_POST_BAD_TYPE = "⚠️ Faqat matn, rasm yoki video yuboring."
CT_PICK_POST_INTERVAL = "⏱ <b>E'lon necha soatda bir marta yuborilsin?</b>"
CT_POST_INTERVAL_LABEL = "Har {h} soatda"
CT_BTN_POST = "📌 E'lonni sozlash"
CT_BTN_POST_NOW = "📤 E'lonni hozir yuborish"
CT_POST_SENT_OK = "✅ E'lon yuborildi"
CT_POST_FAIL = "❌ E'lonni yuborib bo'lmadi: {error}\n\nBot o'sha kanal/guruhda admin ekanini tekshiring."
CT_POST_NOT_READY = "E'lon hali sozlanmagan"
CT_EXTRA_POST = "\n📌 E'lon: <b>{chat}</b>, har <b>{h}</b> soatda"
CT_EXTRA_POST_OFF = "\n📌 E'lon kanalga yuborilmaydi"
CT_EXTRA_POST_ERROR = "\n⚠️ E'lon xatosi: {error}"
