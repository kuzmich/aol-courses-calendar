import calendar
from datetime import date, datetime
import enum
import json
from pathlib import Path

from flask import Flask, request, redirect, url_for, render_template
from wtforms import Form, SelectField, SelectMultipleField, DateField, TimeField, StringField
from wtforms.validators import DataRequired, Optional

from make_calendar import get_month_dates, AdminCourses, read_config


DATA_DIR = 'data'

app = Flask(__name__)


class EventType(enum.StrEnum):
    first_step = "Первый шаг"
    happiness = "Счастье"
    art_of_meditation = "Искусство медитации"
    ayurvedic_cooking = "Здоровое питание"
    art_of_silence = "Искусство тишины"
    dsn = "DSN"
    practices = "Поддерживающее занятие"
    practices_vtp = "Поддерживающее занятие для VTP"
    yoga = "Йога"
    yoga_spine = "Йога для позвоночника"
    yoga_joints = "Суставная йога"
    satsang = "Песенный сатсанг"

    @classmethod
    def choices(cls):
        return [(et.name, et.value) for et in cls]


class WeekDay(enum.IntEnum):
    пн = 1
    вт = 2
    ср = 3
    чт = 4
    пт = 5
    сб = 6
    вс = 7

    mon = 1
    tue = 2
    wed = 3
    thu = 4
    fri = 5
    sat = 6
    sun = 7

    @classmethod
    def choices(cls):
        return [(wd.value, wd.name) for wd in cls]


TEACHERS_CHOICES = [
    "Артиш Анжелика",
    "Крылова Зинаида",
    "Кузьминич Алексей",
    "Пашевина Евгения",
    "Федорова Елена",
    "Федоров Олег",
    "Шумакова Ольга",
    "Яскевич Мира"
]


class Month(enum.Enum):
    января = 1
    февраля = 2
    марта = 3
    апреля = 4
    мая = 5
    июня = 6
    июля = 7
    августа = 8
    сентября = 9
    октября = 10
    ноября = 11
    декабря = 12


class MonthName(enum.Enum):
    январь = 1
    февраль = 2
    март = 3
    апрель = 4
    май = 5
    июнь = 6
    июль = 7
    август = 8
    сентябрь = 9
    октябрь = 10
    ноябрь = 11
    декабрь = 12


class EventForm(Form):
    event_type = SelectField('Мероприятие', [DataRequired()], choices=EventType.choices(), name="type")
    start_date = DateField('Дата начала', [DataRequired()], name="start-date")
    end_date = DateField('Дата окончания', [Optional()], name="end-date")
    schedule = SelectMultipleField('Расписание', [Optional()], choices=WeekDay.choices(), coerce=int)
    start_time = TimeField('Время начала', [Optional()], name="start-time")
    place = StringField('Место', [DataRequired()])
    teachers = SelectMultipleField('Учителя', [Optional()], choices=TEACHERS_CHOICES)


def weekdays_in_month(year: int, month: int, weekday: int):
    """Возвращает все даты определенного дня недели в месяце

    Например, все среды в апреле 2026:

    >>> weekdays_in_month(2026, 4, calendar.WEDNESDAY)
    [date(2026, 4, 1), date(2026, 4, 8), date(2026, 4, 15), date(2026, 4, 22), date(2026, 4, 29)]
    """
    cal = calendar.Calendar()
    return [
        date(year, month, day)
        for week in cal.monthdayscalendar(year, month)
        for day in [week[weekday]]
        if day != 0
    ]


def human_dates(start_date, end_date):
    """Форматирует даты начала и конца события в человеко-читаемом виде

    >>> human_dates(date(2026, 4, 29), date(2026, 5, 3))
    '29 апреля-3 мая'
    """
    month = start_date.month
    if not end_date:
        return f'{start_date.day} {Month(month).name}'
    else:
        month2 = end_date.month
        if month2 == month:
            return f'{start_date.day}-{end_date.day} {Month(month).name}'
        else:
            return f'{start_date.day} {Month(month).name}-{end_date.day} {Month(month2).name}'


def swap_name_and_last_name(full_name):
    last_name, name = full_name.split()
    return f'{name} {last_name}'


def field_to_human(field, value):
    """Форматирует значения формы добавления события в человеко-читаемый вид

    name:
        'happiness' => 'Счастье'
    date:
        (date(2026, 4, 29), date(2026, 5, 3)) => '4 Апреля-5 Мая'
    place:
        'Театральная, 17' => 'Театральная, 17'
    time:
        time(9, 0) => '09:00'
    teachers:
        ['Артиш Анжелика', 'Кузьминич Алексей'] => 'Анжелика Артиш, Алексей Кузьминич'
    """
    match field:
        case "name":
            return EventType[value].value
        case "date":
            return human_dates(*value)
        case "place":
            return value
        case "time":
            return value.strftime('%H:%M')
        case "teachers":
            return ", ".join(map(swap_name_and_last_name, value))
        case _:
            return value


def make_event(form_data):
    event_data = {
        "name": field_to_human("name", form_data['event_type']),
        "date": field_to_human("date", (form_data['start_date'], form_data['end_date'])),
        "place": field_to_human("place", form_data['place']),
    }

    if form_data['teachers']:
       event_data['teachers'] = field_to_human("teachers", form_data['teachers'])
    if form_data['start_time']:
       event_data["time"] = field_to_human("time", form_data['start_time'])

    return event_data


def make_recurring_events(form_data):
    start_date = form_data['start_date']
    end_date = form_data['end_date']
    year = start_date.year
    month = start_date.month

    base_fields = {
        "name": field_to_human("name", form_data['event_type']),
        "time": field_to_human("time", form_data['start_time']),
        "place": field_to_human("place", form_data['place'])
    }

    for weekday in form_data['schedule']:
        for event_dt in weekdays_in_month(year, month, weekday - 1):
            if event_dt >= start_date and (event_dt <= end_date if end_date else True):
                add_fields = {'date': field_to_human("date", (event_dt, None))}
                if form_data['teachers']:
                    add_fields['teachers'] = field_to_human("teachers", form_data['teachers'])

                yield base_fields | add_fields


def add_events(events, year, month):
    data_file = Path(DATA_DIR) / 'manual' / f'{year}_{month}.json'

    with data_file.open() as f:
        month_events = json.load(f)

    month_events.extend(events)

    with data_file.open('w') as f:
        json.dump(month_events, f, ensure_ascii=False, indent=2)


@app.route("/")
def home_page():
    return redirect(url_for('calendar_page', year=datetime.now().year))


@app.route("/<int:year>.html")
def calendar_page(year):
    config = read_config()
    email = config['EMAIL']
    password = config['PASSWORD']
    adm = AdminCourses((email, password))

    years = [2025, 2026]
    calendar_data = []

    for month in range(1, 12+1):
        calendar_data.append({
            'dates': get_month_dates(year, month),
            'events': adm.get(year, month),
            'month': month,
            'month_name': MonthName(month).name.title(),
            'year': year
        })

    return render_template(
        'page_flask.html',
        calendar_data=calendar_data,
        years=years,
        current_year=year,
        can_edit=True
    )


@app.route("/events/", methods=["POST"])
def events():
    form = EventForm(request.form)

    start_date = form.start_date.data
    year = start_date.year
    month = start_date.month

    if request.method == "POST" and form.validate():
        event_type = form.event_type.data
        schedule = form.schedule.data

        if event_type in ["practices", "practices_vtp", "yoga", "yoga_joints", "yoga_spine"] and schedule:
            events = list(make_recurring_events(form.data))
            for event in events:
                print(event)
            add_events(events, year, month)
        else:
            event = make_event(form.data)
            print(event)
            add_events([event], year, month)

        return redirect(url_for('calendar_page', year=year, _anchor=str(month)))
    else:
        return str(form.errors)

