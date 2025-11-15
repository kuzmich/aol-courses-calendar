import calendar
from datetime import date, timedelta
from itertools import groupby
import json
import logging
from pathlib import Path
import re

import dotenv

from aa.proxy.admin import log_in, find_courses
from jinja2 import Environment, FileSystemLoader, select_autoescape


logger = logging.getLogger(__name__)


def render_calendar(context, template_file):
    env = Environment(
        loader=FileSystemLoader("templates"),
        autoescape=select_autoescape()
    )
    template = env.get_template(template_file)
    return template.render(context)


def write_to_file(output, output_file):
    with open(output_file, 'wt') as f:
        f.write(output)

    logger.info('Записано %d байт в файл %s', len(output), output_file)


def get_month_dates(year, month):
    """Возвращает даты текущего месяца, сгрупированные по неделям"""
    cal = calendar.Calendar()

    # >>> cal.monthdatescalendar(2025, 10)
    # [[datetime.date(2025, 9, 29),
    #   datetime.date(2025, 9, 30),
    #   datetime.date(2025, 10, 1),
    #   datetime.date(2025, 10, 2),
    #   datetime.date(2025, 10, 3),
    #   datetime.date(2025, 10, 4),
    #   datetime.date(2025, 10, 5)],
    #  [datetime.date(2025, 10, 6),
    #   datetime.date(2025, 10, 7),
    #   datetime.date(2025, 10, 8),
    #   datetime.date(2025, 10, 9),
    #   datetime.date(2025, 10, 10),
    #   datetime.date(2025, 10, 11),
    #   datetime.date(2025, 10, 12)],
    #  ...
    return cal.monthdatescalendar(year, month)


def _month_week():
    """Closure для month_week"""
    # кеш соответствия даты месяца и недели месяца
    # {(2025, 10): {(9, 29): 1, (9, 30): 1,
    #               (10, 1): 1, (10, 2): 1, (10, 3): 1, (10, 4): 1, (10, 5): 1, (10, 6): 2, (10, 7): 2,
    #               ...,
    #               (10, 31): 5, (11, 1): 5, (11, 2): 5},
    #  ...}
    day_week_map = {
    }

    def month_week(d, month):
        """Возвращает для даты номер недели внутри месяца"""

        year, month = d.year, month
        if (year, month) not in day_week_map:
            cal = calendar.Calendar()
            # для каждой даты календарного месяца посчитаем, какая это неделя
            day_week_map[(year, month)] = {
                (dt.month, dt.day): week
                for week, dates in enumerate(cal.monthdatescalendar(year, month), 1)
                for dt in dates
            }
        return day_week_map[(year, month)][(d.month, d.day)]

    return month_week

month_week = _month_week()


def get_cal_blocks(start_date, end_date):
    """Возвращает блоки дней для каждой недели события, не выходящие за рамки месяца"""

    # (datetime.date(2025, 10, 25), datetime.date(2025, 10, 28)) ->
    # [{'week': 4, 'start': 6, 'end': 7},
    #  {'week': 5, 'start': 1, 'end': 2}]
    # Т.е. для события с 25 по 28 октября 2025 вернется два блока:
    # сб, вс на 4 неделе и пн, вт для 5 недели
    month = start_date.month
    start_week = month_week(start_date, month)

    # последняя дата в месяце (может быть из следующего месяца)
    last_date = calendar.Calendar().monthdatescalendar(start_date.year, month)[-1][-1]

    dates = [
        dt
        for i in range((end_date - start_date).days + 1)
        # не выходим за границы календаря текущего месяца
        if (dt := start_date + timedelta(days=i)) <= last_date
    ]
    for week, group in groupby(dates, lambda d: month_week(d, month)):
        # если переходим в другой месяц, то заканчиваем
        if week < start_week:
            break
        block_dates = list(group)
        yield {'week': week, 'start': block_dates[0].isoweekday(), 'end': block_dates[-1].isoweekday()}


class AdminCourses:
    """Курсы из админки сайта artofliving.ru"""

    course_name_type = {
        'счастье': 'happiness',
        'счастье (благотворительный)': 'happiness',
        'блессинг': 'blessing',
        'yes!': 'yes',
        'yes+': 'yes',
        'art excel': 'art_excel',
        'процесс интуиции': 'intuition',
        'процесс интуиции 5-8 лет': 'intuition',
        'процесс интуиции 8-18 лет': 'intuition',
        'поддерживающее занятие': 'practices',
        'поддерживающее занятие online': 'practices',
        '🎸 песенный сатсанг': 'satsang',
        'глубокий сон и снятие тревожности': 'deep_sleep',
        'искусство тишины': 'art_of_silence',
        'искусство тишины online': 'art_of_silence',
        'искусство тишины интенсив': 'art_of_silence',
        'искусство медитации': 'art_of_meditation',
        'шри шри йога': 'ssy',
        'шри шри йога 2': 'ssy',
        'здоровое питание': 'cooking',
        'победи зависимость': 'give_up_smoking',
        # 'процесс вечности': 'eternity',
        # 'саньям': 'sanyam',
    }

    _sess = None

    def __init__(self, credentials, data_dir='data'):
        self.credentials = credentials
        self.data_dir = Path(data_dir)

    def _get_course_type(self, name):
        return self.course_name_type.get(name.lower(), 'unknown')

    def _parse_dates(self, date_str, year):
        """
        Парсит строку в одну или две даты в зависимости от формата.

        Args:
            date_str (str): Строка с датой или диапазоном дат.
            Примеры: '31 Октября-2 Ноября', '17-19 Октября', '19 Октября'.

        Returns:
            list: Список объектов datetime.date.
            Например: [datetime.date(2025, 10, 31), datetime.date(2025, 11, 2)]
        """

        # Словарик для перевода названий месяцев
        month_map = {
            'января': 1, 'февраля': 2, 'марта': 3, 'апреля': 4,
            'мая': 5, 'июня': 6, 'июля': 7, 'августа': 8,
            'сентября': 9, 'октября': 10, 'ноября': 11, 'декабря': 12
        }

        # Регулярные выражения для разных форматов
        # 1. '31 Октября-2 Ноября'
        pattern_full_range = r'(\d+)\s+([А-Яа-я]+)[-–](\d+)\s+([А-Яа-я]+)'
        # 2. '17-19 Октября'
        pattern_month_range = r'(\d+)[-–](\d+)\s+([А-Яа-я]+)'
        # 3. '19 Октября'
        pattern_single_date = r'(\d+)\s+([А-Яа-я]+)'

        # Попытка найти совпадение по регулярным выражениям
        match_full_range = re.match(pattern_full_range, date_str, re.IGNORECASE)
        match_month_range = re.match(pattern_month_range, date_str, re.IGNORECASE)
        match_single_date = re.match(pattern_single_date, date_str, re.IGNORECASE)

        # Обработка совпадений
        if match_full_range:
            day1_str, month1_str, day2_str, month2_str = match_full_range.groups()
            month1 = month_map[month1_str.lower()]
            month2 = month_map[month2_str.lower()]

            date1 = date(year, month1, int(day1_str))
            date2 = date(year, month2, int(day2_str))
            return [date1, date2]

        elif match_month_range:
            day1_str, day2_str, month_str = match_month_range.groups()
            month = month_map[month_str.lower()]

            date1 = date(year, month, int(day1_str))
            date2 = date(year, month, int(day2_str))
            return [date1, date2]

        elif match_single_date:
            day_str, month_str = match_single_date.groups()
            month = month_map[month_str.lower()]

            single_date = date(year, month, int(day_str))
            return [single_date]

        else:
            raise ValueError(f"Неизвестный формат строки: '{date_str}'")

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

    def _courses2events(self, courses, year):
        def parse(courses):
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
                    'type': self._get_course_type(c['name']),
                    'dates': self._parse_dates(c['date'], year),
                    'dates_str': c['date'],
                    'place': c['place'],
                    'teachers': self._parse_teachers(c.get('teachers', '')),
                    'teachers_str': c.get('teachers', ''),
                    'num_payments': c.get('num_payments', None),
                }
                if 'time' in c:
                    data['time'] = c['time']
                yield data

        def make_cal_blocks(events):
            # [
            #     {'name': 'Счастье Артиш + Кузьминич',
            #      'type': 'happiness',
            #      'pos': {'week': 3, 'start': 5, 'end': 7, 'index': 1}},
            #     {'name': 'YES!',
            #      'type': 'yes',
            #      'pos': {'week': 4, 'start': 6, 'end': 7, 'index': 1}},
            #     {'name': 'YES!',
            #      'type': 'yes',
            #      'pos': {'week': 5, 'start': 1, 'end': 2, 'index': 1}},
            # ]
            for e in events:
                for i, block in enumerate(get_cal_blocks(e['dates'][0], e['dates'][-1]), 1):
                    block['index'] = i
                    yield e | {'pos': block}

        def assign_levels(events):
            events = sorted(events, key=lambda e: e['pos']['start'])
            levels = []  # [(end, level_index), ...]
            next_level = 1

            for event in events:
                start, end = event['pos']['start'], event['pos']['end']

                # пробуем найти уровень, где текущее событие помещается
                for i, l in enumerate(levels, 1):
                    if l[0] < start:
                        levels[i-1] = (end, i)
                        event['pos']['index'] = i
                        break
                else:
                    levels.append((end, next_level))
                    event['pos']['index'] = next_level
                    next_level += 1

            return events

        actual = (c for c in courses if not (c.get('status') == "Не опубликован" and c.get('num_payments') == 0))
        parsed = (e for e in parse(actual))
        # parsed = (e for e in parsed if e['type'] != 'practices')  # временно уберем поддерживающие занятия
        blocks = (e for e in make_cal_blocks(parsed))
        blocks = sorted(blocks, key=lambda e: (e['pos']['week'], e['pos']['start']))
        indexed = []
        for _, group in groupby(blocks, lambda e: e['pos']['week']):
            indexed.extend(assign_levels(group))

        return indexed

    def _save(self, filename, courses):
        with filename.open('wt') as f:
            json.dump(courses, f, indent=2, ensure_ascii=False)

    def _load(self, filename):
        with filename.open('rt') as f:
            return json.load(f)

    def get(self, year, month):
        admin_file = self.data_dir / f'{year}_{month}.json'
        manual_file = self.data_dir / 'manual' / f'{year}_{month}.json'
        courses = []

        if admin_file.exists():
            try:
                courses = self._load(admin_file)
            except Exception as e:
                logger.warning("Не могу загрузить data-файл : %s", admin_file, e)
        else:
            courses = self._get_courses(year, month)
            self._save(admin_file, courses)

        if manual_file.exists():
            try:
                courses.extend(self._load(manual_file))
            except Exception as e:
                logger.warning("Не могу загрузить data-файл : %s", manual_file, e)

        events = self._courses2events(courses, year)
        return events


def read_config():
    return dotenv.dotenv_values()


if __name__ == "__main__":
    logging.basicConfig(level='DEBUG')

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
                'events': adm.get(year, month),
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
