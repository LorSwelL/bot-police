class FieldNames:
    NAME = "Имя"
    SURNAME = "Фамилия"
    STATIC_ID = "Статик ID"
    REASON = "Причина"
    APPROVAL = "Одобрение"
    RANK = "Звание"
    STATUS = "Статус"
    OFFICER = "Сотрудник"
    REJECT_REASON = "Причина отказа"
    NEW_RANK = "Новое звание"
    FULL_NAME = "ФИО"

class StatusValues:
    PENDING = "⏳ ожидает"
    ACCEPTED = "✅ принято"
    REJECTED = "❌ отклонено"
    FIRED = "✅ уволен"
    PROMOTED = "✅ повышен"

class EmbedTitles:
    CADET = "👤 Курсант"
    TRANSFER = "🔄 Перевод"
    GOV = "🏛️ Гос сотрудник"
    FIRING = "РАПОРТ ОБ УВОЛЬНЕНИИ"
    PROMOTION = "РАПОРТ О ПОВЫШЕНИИ"

class ExamMessages:
    # Источник истины для текстов экзамена/приветствия — Config (EXAM_WELCOME_*, EXAM_ORDER_TEXT, EXAM_HERB_URL, EXAM_SEAL_URL).
    # Значения ниже — fallback при отсутствии Config или до его загрузки.
    MONTHS = {
        1: "января", 2: "февраля", 3: "марта", 4: "апреля",
        5: "мая", 6: "июня", 7: "июля", 8: "августа",
        9: "сентября", 10: "октября", 11: "ноября", 12: "декабря"
    }

    HERB_URL = ""
    SEAL_URL = ""

    WELCOME_TITLE = "🎓 Вы приняты на службу"
    WELCOME_SUBTITLE = "Управление внутренних дел • Кадровый департамент"

    WELCOME_HEADER = ""
    WELCOME_TEXT = (
        "**ПРИКАЗ № {report_id}**\n"
        "от {day} {month} {year} г.\n\n"
        "**ПРИКАЗЫВАЮ:**\n"
        "1. Зачислить **{name}** в Академию УВД.\n"
        "2. Присвоить статус «Курсант».\n"
        "3. Направить для прохождения вступительных испытаний.\n\n"
        "_Основание: рапорт №{report_id}_"
    )


    HEADER = "Управление внутренних дел • Кадровый департамент"
    EXAM_NOTIFICATION = (
        "{header}\n\n"
        "Дата: {date}\n"
        "Участник: **{name}**\n\n"
        "{greeting}"
    )
    CONGRATS = (
        "Добро пожаловать! Ожидайте дальнейших указаний.",
        "Удачи на экзамене!",
    )