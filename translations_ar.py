"""Arabic translations for the interface. See i18n.py for how they are used.

EXACT maps fixed English text to Arabic. TEMPLATES does the same for text with
inserted values: {0}, {1}... stand for the values, in the order they appear in
the English sentence, and may be reordered in the Arabic one.
"""

EXACT = {
    # sidebar and page titles
    "Sorter": "الفرز",
    "Duplicates": "الملفات المكررة",
    "History": "السجل",
    "Settings": "الإعدادات",
    "About": "حول",
    "Updates": "التحديثات",

    # common buttons
    "Refresh": "تحديث",
    "OK": "موافق",
    "Cancel": "إلغاء",
    "Apply": "تطبيق",
    "Add…": "إضافة…",
    "Edit…": "تعديل…",
    "Remove": "إزالة",
    "Browse…": "استعراض…",
    "Later": "لاحقًا",
    "Done": "تم",
    "Search": "بحث",
    "Undo": "تراجع",
    "Update": "تحديث",
    "Exit": "خروج",
    "Open": "فتح",
    "Stop": "إيقاف",
    "Scan": "فحص",
    "Clear": "مسح",
    "Check": "تحديد",
    "Uncheck": "إلغاء التحديد",
    "Delete": "حذف",
    "Delete…": "حذف…",
    "Check…": "تحديد…",

    # column headings
    "File": "الملف",
    "In": "في",
    "Age (days)": "العمر (أيام)",
    "Size": "الحجم",
    "Goes to": "الوجهة",
    "When": "الوقت",
    "From": "من",
    "To": "إلى",
    "Status": "الحالة",
    "Folder": "المجلد",
    "Full path": "المسار الكامل",
    "Modified": "آخر تعديل",
    "Moved to": "نُقل إلى",
    "Destination folder": "مجلد الوجهة",
    "Extensions": "الامتدادات",
    "Move after": "النقل بعد",
    "Clean up after": "التنظيف بعد",
    "Action": "الإجراء",

    # cell values
    "Moved": "منقول",
    "Undone": "تم التراجع",
    "Deleted": "محذوف",
    "Restored": "مستعاد",
    "Erased": "محذوف نهائيًا",
    "Recycle Bin": "سلة المحذوفات",
    "Deleted for good": "حُذف نهائيًا",
    "Keep": "إبقاء",
    "general": "العام",
    "never": "أبدًا",

    # Sorter page
    "Show all files (ignore age)": "عرض كل الملفات (تجاهل العمر)",
    "Exclude selected": "استثناء المحدد",
    "Undo last move": "تراجع عن آخر نقل",
    "Move selected": "نقل المحدد",
    "Move files": "نقل الملفات",
    "Sort ALL files now (ignore age)": "فرز كل الملفات الآن (تجاهل العمر)",
    "Nothing to move: no files are old enough yet": "لا شيء للنقل: لا توجد ملفات قديمة كفاية بعد",
    "No files to sort": "لا توجد ملفات للفرز",
    "Move only the selected file(s) now": "نقل الملفات المحددة فقط الآن",
    "Never move this file": "عدم نقل هذا الملف أبدًا",
    "Show in File Explorer": "إظهار في مستكشف الملفات",
    "Open / Run": "فتح / تشغيل",
    "Delete (to Recycle Bin)": "حذف (إلى سلة المحذوفات)",
    "Select one or more files in the list first (Ctrl or Shift for several).":
        "حدّد ملفًا أو أكثر من القائمة أولًا (استخدم Ctrl أو Shift لتحديد عدة ملفات).",
    "There are no files to sort.": "لا توجد ملفات للفرز.",
    "There is no move to undo.": "لا توجد عملية نقل للتراجع عنها.",
    "This file is not there any more.": "هذا الملف لم يعد موجودًا.",
    "Sort all": "فرز الكل",
    "Sort folder": "فرز المجلد",

    # History page
    "Rows per page": "عدد الصفوف في الصفحة",
    "‹ Previous": "‹ السابق",
    "Next ›": "التالي ›",
    "Undo selected": "تراجع عن المحدد",
    "Select rows with Ctrl or Shift (Ctrl+A for the whole page). Undo puts moved files back and brings deleted "
    "files out of the Recycle Bin.":
        "حدّد الصفوف باستخدام Ctrl أو Shift (و Ctrl+A لتحديد الصفحة كلها). التراجع يعيد الملفات المنقولة إلى مكانها "
        "ويستعيد الملفات المحذوفة من سلة المحذوفات.",
    "Select one or more rows with the status Moved or Deleted.": "حدّد صفًا أو أكثر حالته «منقول» أو «محذوف».",

    # Settings page
    "Folders to sort": "المجلدات المراد فرزها",
    "Move files older than (days)": "نقل الملفات الأقدم من (أيام)",
    "a category can have its own number": "يمكن تحديد رقم خاص لكل تصنيف",
    "Background check every (minutes)": "الفحص في الخلفية كل (دقائق)",
    "0 turns automatic sorting off": "القيمة 0 توقف الفرز التلقائي",
    "After an automatic run": "بعد كل فرز تلقائي",
    "Show a report window": "عرض نافذة تقرير",
    "Only a tray notification": "إشعار فقط",
    "Folder for all other file types": "مجلد لباقي أنواع الملفات",
    "leave blank to leave those files alone": "اتركه فارغًا لعدم نقل تلك الملفات",
    "Never move (names or patterns)": "عدم النقل أبدًا (أسماء أو أنماط)",
    "e.g. *.torrent, taxes*": "مثال: ‎*.torrent, taxes*",
    "Categories": "التصنيفات",
    "Save settings": "حفظ الإعدادات",
    "Language": "اللغة",
    "Sort only this folder now": "فرز هذا المجلد فقط الآن",
    "Days and minutes must be whole numbers, 0 or more.": "الأيام والدقائق يجب أن تكون أعدادًا صحيحة، 0 أو أكثر.",
    "Settings saved. The Sorter page shows the result.": "تم حفظ الإعدادات. صفحة «الفرز» تعرض النتيجة.",
    "Settings saved. The Sorter page shows the result.\n\nAutomatic sorting has been turned off because the interval is 0.":
        "تم حفظ الإعدادات. صفحة «الفرز» تعرض النتيجة.\n\nتم إيقاف الفرز التلقائي لأن الفاصل الزمني 0.",
    "Settings saved. The window will reopen in the new language.": "تم حفظ الإعدادات. ستُعاد فتح النافذة باللغة الجديدة.",

    # category dialog
    "Category": "تصنيف",
    "A plain name creates the folder inside the folder being sorted.": "الاسم المجرد يُنشئ المجلد داخل المجلد الذي يُفرز.",
    "File extensions (separated by spaces or commas)": "امتدادات الملفات (تفصل بينها مسافات أو فواصل)",
    "Move these files after (days)": "نقل هذه الملفات بعد (أيام)",
    "Leave blank to use the general setting.": "اتركه فارغًا لاستخدام الإعداد العام.",
    "Clean up: send to the Recycle Bin after (days in this folder)": "التنظيف: الإرسال إلى سلة المحذوفات بعد (أيام في هذا المجلد)",
    "0 = never. Only files this program moved here are cleaned up,\nand you can bring them back from the History tab.":
        "0 = أبدًا. لا يُنظَّف إلا ما نقله البرنامج نفسه إلى هنا،\nويمكنك استعادته من صفحة «السجل».",
    "Days must be whole numbers, 0 or more.": "الأيام يجب أن تكون أعدادًا صحيحة، 0 أو أكثر.",
    "Enter a folder and at least one extension.": "أدخل مجلدًا وامتدادًا واحدًا على الأقل.",

    # status bar and automatic sorting
    "Automatic sorting": "الفرز التلقائي",
    "Automatic sorting is ON (see the icon in the taskbar tray)": "الفرز التلقائي يعمل (انظر الأيقونة بجانب الساعة)",
    "Automatic sorting is OFF: the check interval is set to 0": "الفرز التلقائي متوقف: الفاصل الزمني للفحص 0",
    "Automatic sorting is OFF: nothing moves until you click Move": "الفرز التلقائي متوقف: لا يُنقل شيء حتى تضغط «نقل»",
    "Turn on automatic sorting": "تشغيل الفرز التلقائي",
    "Turn off automatic sorting": "إيقاف الفرز التلقائي",
    "Pause for today": "إيقاف مؤقت لليوم",
    "Resume": "استئناف",
    "Resume sorting": "استئناف الفرز",
    "The check interval is 0, which keeps automatic sorting off.\n\nSet it to 1 or more in Settings, save, then turn it on.":
        "الفاصل الزمني للفحص 0، وهذا يُبقي الفرز التلقائي متوقفًا.\n\nاجعله 1 أو أكثر في الإعدادات واحفظ، ثم شغّله.",
    "automatic sorting is on": "الفرز التلقائي يعمل",
    "automatic sorting is off": "الفرز التلقائي متوقف",

    # tray menu and notifications
    "Open Downloads Sorter": "فتح Downloads Sorter",
    "Sort now": "افرز الآن",
    "Show report": "عرض التقرير",
    "Install update": "تثبيت التحديث",
    "The update could not be downloaded. It will be tried again later.": "تعذّر تنزيل التحديث. ستُعاد المحاولة لاحقًا.",

    # About page and updates
    "Keeps your Downloads folder tidy by moving old files into category folders, automatically or only when you say so. "
    "Every change is logged and can be undone.":
        "يحافظ على ترتيب مجلد التنزيلات بنقل الملفات القديمة إلى مجلدات مصنّفة، تلقائيًا أو فقط عندما تطلب ذلك. "
        "كل تغيير يُسجَّل ويمكن التراجع عنه.",
    "GitHub page": "صفحة GitHub",
    "Open settings and log folder": "فتح مجلد الإعدادات والسجل",
    "Not checked yet.": "لم يتم التحقق بعد.",
    "Check for updates": "التحقق من التحديثات",
    "Checking for updates…": "جارٍ التحقق من التحديثات…",
    "Update now": "حدّث الآن",
    "Install new versions automatically": "تثبيت النسخ الجديدة تلقائيًا",
    "Off: you get a notification and choose when to update. On: while automatic sorting is running, new versions install "
    "by themselves when no Downloads Sorter window is open.":
        "متوقف: يصلك إشعار وتختار أنت وقت التحديث. يعمل: أثناء تشغيل الفرز التلقائي تُثبَّت النسخ الجديدة من تلقاء نفسها "
        "عندما لا تكون أي نافذة للبرنامج مفتوحة.",

    # report window
    "Downloads Sorter: files were moved": "Downloads Sorter: تم نقل ملفات",
    "Approve": "موافقة",
    "Undo all": "تراجع عن الكل",
    "Nothing is waiting for review": "لا شيء بانتظار المراجعة",
    "Approve to keep them where they are now, or Undo to put them all back. Right-click a file for more.":
        "اضغط «موافقة» لإبقائها في مكانها الحالي، أو «تراجع» لإعادتها كلها. انقر بالزر الأيمن على ملف لخيارات أكثر.",

    # Duplicates page
    "Look in": "ابحث في",
    "Match by": "المطابقة حسب",
    "Include subfolders": "تضمين المجلدات الفرعية",
    "Show only": "عرض فقط",
    "The sorted folders": "المجلدات المفروزة",
    "This folder:": "هذا المجلد:",
    "Check in": "التحديد في",
    "Use scan folder": "استخدام مجلد الفحص",
    "Check copies in this folder": "تحديد النسخ في هذا المجلد",
    "Keep first, delete the rest": "إبقاء الأول وحذف الباقي",
    "Keep newest, delete the rest": "إبقاء الأحدث وحذف الباقي",
    "Delete checked": "حذف المحدد",
    "Delete for good": "حذف نهائي",
    "Move to Recycle Bin": "نقل إلى سلة المحذوفات",
    "Remove from this list (keeps the file)": "إزالة من هذه القائمة (مع إبقاء الملف)",
    "Choose where to look and how to compare, then click Scan.": "اختر مكان البحث وطريقة المقارنة، ثم اضغط «فحص».",
    "Choose the folder to look in first.": "اختر المجلد المراد البحث فيه أولًا.",
    "Folder to look for duplicates in": "المجلد المراد البحث فيه عن المكررات",
    "Folder whose copies to check": "المجلد المراد تحديد نسخه",
    "Enter a folder in \"Check in\", or click Use scan folder.": "أدخل مجلدًا في «التحديد في»، أو اضغط «استخدام مجلد الفحص».",
    "No group has two copies in the same folder.": "لا توجد مجموعة فيها نسختان في المجلد نفسه.",
    "Files sent to the Recycle Bin can be brought back from History.": "الملفات المرسلة إلى سلة المحذوفات يمكن استعادتها من «السجل».",
    "There is nothing to delete. Check one or more files first (click the box next to a file, or use Check…).":
        "لا يوجد ما يُحذف. حدّد ملفًا أو أكثر أولًا (انقر المربع بجانب الملف، أو استخدم «تحديد…»).",
    "All but the first in each group": "الكل عدا الأول في كل مجموعة",
    "All but the newest in each group": "الكل عدا الأحدث في كل مجموعة",
    "The biggest in each group": "الأكبر في كل مجموعة",
    "The smallest in each group": "الأصغر في كل مجموعة",
    "Every copy inside the \"Check in\" folder": "كل نسخة داخل مجلد «التحديد في»",
    "Extra copies in the same folder (keep 1 per folder)": "النسخ الزائدة في المجلد نفسه (إبقاء واحدة لكل مجلد)",
    "Highlighted rows": "الصفوف المظللة",
    "Check all": "تحديد الكل",
    "Uncheck all": "إلغاء تحديد الكل",
    "Invert": "عكس التحديد",
    "Name contains": "الاسم يحتوي",
    "Extension": "الامتداد",
    "At least (MB)": "على الأقل (ميغابايت)",
    "Scan stopped.": "توقف الفحص.",
    "Stopping…": "جارٍ الإيقاف…",
    "The scan failed.": "فشل الفحص.",
}

TEMPLATES = {
    # Sorter page
    "{0} file(s) ready to move ({1})": "{0} ملف جاهز للنقل ({1})",
    "{0} file(s) of any age ({1}): select the ones to sort": "{0} ملف من أي عمر ({1}): حدّد ما تريد فرزه",
    "Move {0} file(s)": "نقل {0} ملف",
    "Move the {0} listed file(s)?": "هل تريد نقل الملفات المعروضة وعددها {0}؟",
    "Move only the {0} selected file(s)?": "هل تريد نقل الملفات المحددة فقط وعددها {0}؟",
    "Move all {0} file(s) now, including new ones and ones you put back with Undo?\n\n"
    "Files on the never-move list stay. You can undo this from History.":
        "هل تريد نقل كل الملفات وعددها {0} الآن، بما فيها الجديدة والتي أعدتها بالتراجع؟\n\n"
        "الملفات في قائمة «عدم النقل» تبقى. يمكنك التراجع عن ذلك من «السجل».",
    "Put back the {0} file(s) moved on {1}?": "هل تريد إعادة {0} ملف نُقلت في {1}؟",
    "Moved {0} file(s).": "تم نقل {0} ملف.",
    "Restored {0} file(s).": "تمت استعادة {0} ملف.",
    "Restored {0} file(s). They will not be moved again automatically.": "تمت استعادة {0} ملف. لن تُنقل تلقائيًا مرة أخرى.",
    "{0}\n\n{1} failed:\n{2}": "{0}\n\nفشل {1}:\n{2}",
    "Move this file to the Recycle Bin?\n\n{0}\n\nYou can bring it back from the History tab.":
        "هل تريد نقل هذا الملف إلى سلة المحذوفات؟\n\n{0}\n\nيمكنك استعادته من صفحة «السجل».",
    "Could not delete it:\n{0}": "تعذّر حذفه:\n{0}",
    "Could not open it:\n{0}": "تعذّر فتحه:\n{0}",
    "Nothing to sort in\n{0}\n\nNo files there are old enough yet.": "لا شيء للفرز في\n{0}\n\nلا توجد هناك ملفات قديمة كفاية بعد.",
    "Move {0} file(s) in\n{1}\ninto their category folders?": "هل تريد نقل {0} ملف في\n{1}\nإلى مجلدات تصنيفها؟",

    # History page
    "Page {0} of {1}": "صفحة {0} من {1}",
    "{0} change(s) logged, {1} can be undone": "{0} تغيير مسجَّل، يمكن التراجع عن {1}",
    "{0} match(es) in {1} change(s) logged, {2} can be undone": "{0} نتيجة من {1} تغيير مسجَّل، يمكن التراجع عن {2}",
    "Undo {0} change(s)?": "هل تريد التراجع عن {0} تغيير؟",

    # Settings
    "Downloads (automatic): {0}": "التنزيلات (تلقائي): {0}",
    "{0} days": "{0} يوم",

    # status bar and automatic sorting
    "Automatic sorting is PAUSED until {0}": "الفرز التلقائي متوقف مؤقتًا حتى {0}",
    "paused until {0}": "متوقف مؤقتًا حتى {0}",
    "The {0} file(s) on the Sorter page will be moved now, and from then on files will be checked every {1} minutes "
    "and moved without asking.\n\nAfter each run you can review, approve or undo what moved.\n\n"
    "It starts by itself every time you sign in to Windows.\n\nTurn it on?":
        "سيتم الآن نقل الملفات المعروضة في صفحة «الفرز» وعددها {0}، وبعد ذلك تُفحص الملفات كل {1} دقيقة وتُنقل دون سؤال.\n\n"
        "بعد كل عملية يمكنك مراجعة ما نُقل والموافقة عليه أو التراجع عنه.\n\n"
        "يبدأ تلقائيًا مع كل تسجيل دخول إلى ويندوز.\n\nهل تريد تشغيله؟",

    # tray notifications
    "Install version {0}": "تثبيت النسخة {0}",
    "Moved {0} file(s). Open History to review or undo.": "تم نقل {0} ملف. افتح «السجل» للمراجعة أو التراجع.",
    "Sent {0} old file(s) to the Recycle Bin. You can bring them back from History.":
        "أُرسل {0} ملف قديم إلى سلة المحذوفات. يمكنك استعادتها من «السجل».",
    "Version {0} is available. Right-click this icon and choose Install, or open {1}.":
        "النسخة {0} متوفرة. انقر بالزر الأيمن على هذه الأيقونة واختر «تثبيت»، أو افتح {1}.",
    "Downloading version {0}…": "جارٍ تنزيل النسخة {0}…",
    "Updated to version {0}.": "تم التحديث إلى النسخة {0}.",

    # About page and updates
    "Version {0}": "النسخة {0}",
    "Version {0}  ·  MIT License": "النسخة {0}  ·  رخصة MIT",
    "Version {0} is available (you have {1}).": "النسخة {0} متوفرة (لديك {1}).",
    "No newer version found. You have version {0}.": "لا توجد نسخة أحدث. لديك النسخة {0}.",
    "Download and install version {0} now?\n\n{1} will close and reopen by itself.":
        "هل تريد تنزيل النسخة {0} وتثبيتها الآن؟\n\nسيُغلق {1} ثم يُفتح من تلقاء نفسه.",
    "The download failed: {0}": "فشل التنزيل: {0}",

    # report window
    "{0} file(s) were moved automatically": "تم نقل {0} ملف تلقائيًا",

    # Duplicates page
    "Group {0}:  {1} files": "المجموعة {0}:  {1} ملفات",
    "Delete {0} checked": "حذف {0} محدد",
    "Deleted {0} file(s) for good.": "تم حذف {0} ملف نهائيًا.",
    "Sent {0} file(s) to the Recycle Bin. You can bring them back from History.":
        "أُرسل {0} ملف إلى سلة المحذوفات. يمكنك استعادتها من «السجل».",
    "The {0} file(s) will be gone for good: they won't go to the Recycle Bin and History can't bring them back.\n\nDelete them?":
        "سيُحذف {0} ملف نهائيًا: لن تذهب إلى سلة المحذوفات ولن يستطيع «السجل» استعادتها.\n\nهل تريد حذفها؟",
    "None of the listed files are in\n{0}": "لا يوجد أي من الملفات المعروضة في\n{0}",
    "Not a folder:\n{0}": "ليس مجلدًا:\n{0}",
    "The scan failed:\n{0}": "فشل الفحص:\n{0}",
}
