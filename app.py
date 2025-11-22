import calendar
from datetime import date, datetime, timedelta
import enum
from functools import cache
import json
from pathlib import Path

from bson.objectid import ObjectId
from flask import Flask, request, redirect, url_for, render_template
from pymongo import MongoClient
from wtforms import Form, SelectField, SelectMultipleField, DateField, TimeField, StringField
from wtforms.validators import DataRequired, Optional
from wtforms.widgets import CheckboxInput, ListWidget

from cal_utils import prepare_events, get_month_dates, next_month_first_day, weekdays_in_month


DATA_DIR = 'data'

app = Flask(__name__)


class EventType(enum.StrEnum):
    first_step = "Первый шаг"
    happiness = "Счастье"
    art_of_meditation = "Искусство медитации"
    cooking = "Здоровое питание"
    art_of_silence = "Искусство тишины"
    dsn = "DSN"
    practices = "Поддерживающее занятие"
    practices_vtp = "Поддерживающее занятие для VTP"
    yoga = "Йога"
    yoga_spine = "Йога для позвоночника"
    yoga_joints = "Суставная йога"
    satsang = "Песенный сатсанг"
    premium = "Искусство жизни — Премиум"

    @classmethod
    def choices(cls, sort=True, empty_option="Не выбрано"):
        event_types = [(et.name, et.value) for et in cls]
        if sort:
            event_types = sorted(event_types, key=lambda et: et[1])
        if empty_option:
            event_types.insert(0, ("", empty_option))
        return event_types


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
    "Глебова Лариса",
    "Девятайкина Елена",
    "Демиденко Ольга",
    "Копанев Вадим",
    "Крылова Зинаида",
    "Кузьминич Алексей",
    "Маслов Андрей",
    "Пашевина Евгения",
    "Ружьева Анна",
    "Федорова Елена",
    "Федоров Олег",
    "Цыкунова Галина",
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


class MultiCheckboxField(SelectMultipleField):
    """
    A multiple-select, except displays a list of checkboxes.

    Iterating the field will produce subfields, allowing custom rendering of
    the enclosed checkbox fields.
    """
    widget = ListWidget(prefix_label=False)
    option_widget = CheckboxInput()


class EventForm(Form):
    event_type = SelectField('Мероприятие', [DataRequired()], choices=EventType.choices(), name="type")
    start_date = DateField('Дата начала', [DataRequired()], name="start-date")
    end_date = DateField('Дата окончания', [Optional()], name="end-date")
    schedule = MultiCheckboxField('Расписание', [Optional()], choices=WeekDay.choices(), coerce=int)
    start_time = TimeField('Время начала', [Optional()], name="start-time")
    place = StringField('Место', [DataRequired()])
    teachers = SelectMultipleField('Учителя', [Optional()], choices=TEACHERS_CHOICES)


def human_dates(start_date, end_date):
    """Форматирует даты начала и конца события в человеко-читаемом виде

    >>> human_dates(date(2026, 4, 29), date(2026, 5, 3))
    '29 апреля-3 мая'
    """
    month = start_date.month
    if not end_date or end_date == start_date:
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


def make_event(form_data, **override):
    """Подготавливает данные из формы добавления/редактирования для сохранения в базу"""

    data = form_data | override

    event_data = {
        "name": EventType[data["event_type"]].value,
        "type": data["event_type"],
        "dates": human_dates(data["start_date"], data["end_date"]),
        "place": data["place"],
        "start_date": datetime.combine(data["start_date"], datetime.min.time()),
        "end_date": datetime.combine(data["end_date"] or data["start_date"], datetime.min.time()),
    }

    if data['teachers']:
        event_data["teachers"] = data["teachers"]
    if data['start_time']:
        event_data["time"] = data["start_time"].strftime('%H:%M')

    return event_data


def make_recurring_events(form_data):
    start_date = form_data['start_date']
    end_date = form_data['end_date']

    for weekday in form_data['schedule']:
        for event_dt in weekdays_in_month(start_date.year, start_date.month, weekday - 1):
            if event_dt >= start_date and (event_dt <= end_date if end_date else True):
                yield make_event(form_data, start_date=event_dt, end_date=event_dt)


def add_events(events):
    db = get_db()
    events_col = db['events']

    for e in events:
        events_col.insert_one(e)


@cache
def get_db(url='mongodb://127.0.0.1:27017/', dbname='aol_calendar'):
    client = MongoClient(url)
    return client[dbname]


def get_events(year, month):
    """Получаем события из базы за последний месяц"""
    db = get_db()
    events_col = db['events']
    start_of_month = datetime(year, month, 1)
    cursor = events_col.find(
        {'start_date': {'$gte': start_of_month,
                        '$lt': next_month_first_day(start_of_month)}}
    )
    return [e for e in cursor]


def get_event_by_id(event_id):
    db = get_db()
    events_col = db['events']
    return events_col.find_one({'_id': ObjectId(event_id)})


def save_event(event_id, form):
    db = get_db()
    events_col = db['events']

    events_col.replace_one(
        {'_id': ObjectId(event_id)},
        make_event(form.data)
    )


@app.template_filter()
def teacher_names(teachers):
    names = []
    for t in teachers:
        last_name, first_name = t.split()
        names.append(f'{last_name} {first_name[0]}.')
    return ' + '.join(names)


@app.route("/")
def home_page():
    return redirect(url_for('calendar_page', year=datetime.now().year))


@app.route("/<int:year>.html")
def calendar_page(year):
    years = [2025, 2026]
    calendar_data = []
    form = EventForm()

    for month in range(1, 12+1):
        calendar_data.append({
            'dates': get_month_dates(year, month),
            'events': prepare_events(get_events(year, month)),
            'month': month,
            'month_name': MonthName(month).name.title(),
            'year': year
        })

    return render_template(
        'page.html',
        calendar_data=calendar_data,
        years=years,
        current_year=year,
        can_edit=True,
        form=form
    )


@app.route("/events/", methods=["POST"])
def events():
    """Добавление события"""

    form = EventForm(request.form)
    print(form.data)

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
            add_events(events)
        else:
            event = make_event(form.data)
            print(event)
            add_events([event])

        return redirect(url_for('calendar_page', year=year, _anchor=str(month)))
    else:
        return str(form.errors)


@app.route("/events/<event_id>", methods=["POST"])
def edit_event(event_id):
    """Редактирования события"""

    event = get_event_by_id(event_id)
    form = EventForm(request.form, data=event)
    start_date = event['start_date']

    if form.validate():
        save_event(event_id, form)
        print(form.data)
        return redirect(url_for('calendar_page', year=start_date.year, _anchor=str(start_date.month)))
    else:
        # return str(form.errors)
        return render_template("event-form.html", form=form, edit=True, url=url_for('edit_event', event_id=event_id))


@app.route("/event/form/<event_id>")
def get_event_form(event_id):
    event = get_event_by_id(event_id)
    print(event)

    start_time = None
    if event.get('time'):
        start_time = datetime.strptime(event['time'], "%H:%M")
    form = EventForm(data=event, event_type=event['type'], start_time=start_time)
    return render_template("event-form.html", form=form, edit=True, url=url_for('edit_event', event_id=event_id))
