from datetime import date
import json
import logging
from pathlib import Path

from aa.proxy.admin import log_in, find_courses
import dotenv
from jinja2 import Environment, FileSystemLoader, select_autoescape

from app import get_events, teacher_names
from cal_utils import prepare_events, get_month_dates
from parsing_utils import get_course_type, parse_dates


logger = logging.getLogger(__name__)


def render_calendar(context, template_file):
    env = Environment(
        loader=FileSystemLoader("templates"),
        autoescape=select_autoescape()
    )
    env.filters['teacher_names'] = teacher_names
    template = env.get_template(template_file)
    return template.render(context)


def write_to_file(output, output_file):
    with open(output_file, 'wt') as f:
        f.write(output)

    logger.info('Записано %d байт в файл %s', len(output), output_file)


class AdminCourses:
    """Курсы из админки сайта artofliving.ru"""

    _sess = None

    def __init__(self, credentials, data_dir='data'):
        self.credentials = credentials
        self.data_dir = Path(data_dir)

    def _parse_teachers(self, teachers_str):
        """Возвращает список фамилий учителей

        >>> adm._parse_teachers('Анжелика Артиш, Алексей Кузьминич')
        ['Артиш', 'Кузьминич']
        """
        teachers = []
        teachers_str = teachers_str.strip()
        if not teachers_str:
            return teachers
        for teacher in teachers_str.split(','):
            teachers.append(teacher.strip().split()[-1])
        return teachers

    @property
    def _session(self):
        if not self._sess:
            self._sess = log_in(*self.credentials)
        return self._sess

    def _get_courses(self, year, month):
        # [{'name': 'Блессинг',
        #   'date': '31 Октября-2 Ноября',
        #   'place': 'Театральная, 17',
        #   'teachers': 'Ольга Шумакова',
        #   'num_payments': 9,
        #   'status': 'Стоит в расписании'},
        #  {'name': 'Счастье', 'date': '17-19 Октября', 'place': 'Театральная, 17',
        #   'teachers': 'Анжелика Артиш, Алексей Кузьминич', 'num_payments': 10, 'status': 'Завершён'},
        #  {'name': 'YES!', 'date': '25–28 Октября', 'place': 'Театральная, 17',
        #   'teachers': 'Галина Дианова, Татьяна Шпикалова', 'num_payments': 9, 'status': 'Идет'}
        #  {'name': 'Поддерживающее занятие online', 'date': '19 Октября', 'place': 'Онлайн, время МСК+5',
        #   'num_payments': 9, 'status': 'Завершён'},
        return find_courses(self._session, month=date(year, month, 1))

    def parse(self, courses):
        # [
        #     {'name': 'Счастье',
        #      'type': 'happiness',
        #      'teachers': ['Артиш', 'Кузьминич'],
        #      'dates': [date(2025, 10, 17), date(2025, 10, 19)]},
        #     ...
        # ]
        for c in courses:
            data = {
                'name': c['name'],
                'type': get_course_type(c['name']),
                'dates': parse_dates(c['date'], year),
                'dates_str': c['date'],
                'place': c['place'],
                'teachers': self._parse_teachers(c.get('teachers', '')),
                'teachers_str': c.get('teachers', ''),
                'num_payments': c.get('num_payments', None),
            }
            if 'time' in c:
                data['time'] = c['time']
            yield data

    def prepare(self, events):
        actual = (e for e in events if not (e.get('status') == "Не опубликован" and e.get('num_payments') == 0))
        parsed = (e for e in self.parse(actual))
        # parsed = (e for e in parsed if e['type'] != 'practices')  # временно уберем поддерживающие занятия
        return prepare_events(parsed)

    def _save(self, filename, courses):
        with filename.open('wt') as f:
            json.dump(courses, f, indent=2, ensure_ascii=False)

    def _load(self, filename):
        with filename.open('rt') as f:
            return json.load(f)

    def get(self, year, month):
        admin_file = self.data_dir / f'{year}_{month}.json'
        manual_file = self.data_dir / 'manual' / f'{year}_{month}.json'
        events = []

        if admin_file.exists():
            try:
                events = self._load(admin_file)
            except Exception as e:
                logger.warning("Не могу загрузить data-файл : %s", admin_file, e)
        else:
            events = self._get_courses(year, month)
            self._save(admin_file, events)

        if manual_file.exists():
            try:
                events.extend(self._load(manual_file))
            except Exception as e:
                logger.warning("Не могу загрузить data-файл : %s", manual_file, e)

        return self.prepare(events)


def read_config():
    return dotenv.dotenv_values()


if __name__ == "__main__":
    logging.basicConfig(level='DEBUG')
    logging.getLogger('pymongo').setLevel('INFO')

    template_file = 'page.html'
    output_dir = 'out/'

    config = read_config()
    email = config['EMAIL']
    password = config['PASSWORD']

    month_names = ['январь', 'февраль', 'март',
                   'апрель', 'май', 'июнь',
                   'июль', 'август', 'сентябрь',
                   'октябрь', 'ноябрь', 'декабрь']

    adm = AdminCourses((email, password))

    years = [2025, 2026]

    for year in years:
        calendar_data = []

        for month in range(1, 12+1):
            calendar_data.append({
                'dates': get_month_dates(year, month),
                # 'events': adm.get(year, month),
                'events': prepare_events(get_events(year, month)),
                'month': month,
                'month_name': month_names[month - 1].title(),
                'year': year
            })

        output = render_calendar(
            {'calendar_data': calendar_data,
             'years': years,
             'current_year': year},
            template_file
        )
        write_to_file(output, Path(output_dir) / f'{year}.html')
