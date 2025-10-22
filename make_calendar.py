import calendar
from datetime import date
import logging

from jinja2 import Environment, FileSystemLoader, select_autoescape


logger = logging.getLogger(__name__)


def render_calendar(context, template_file):
    env = Environment(
        loader=FileSystemLoader("."),
        autoescape=select_autoescape()
    )
    template = env.get_template(template_file)
    return template.render(context)


def write_to_file(output, output_file):
    with open(output_file, 'wt') as f:
        f.write(output)

    logger.info('Записано %d байт в файл %s', len(output), output_file)


def get_month_dates(year, month):
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


def get_events(year, month):
    events = [
        {'name': 'Счастье',
         'type': 'happiness',
         'teachers': ['Артиш', 'Кузьминич'],
         'dates': [date(2025, 10, 17), date(2025, 10, 19)]}
    ]
    events_data = [
        {'name': 'Счастье Артиш + Кузьминич',
         'type': 'happiness',
         'pos': {'week': 3, 'start': 5, 'end': 7, 'index': 1}},
        {'name': 'Счастье 2',
         'type': 'happiness',
         'pos': {'week': 3, 'start': 5, 'end': 7, 'index': 2}},
    ]
    return events_data


if __name__ == "__main__":
    logging.basicConfig(level='DEBUG')

    template_file = 'calendar-template.html'
    output_file = 'out/calendar.html'

    month_dates = get_month_dates(2025, 10)

    output = render_calendar(
        {'month_dates': month_dates,
         'events': get_events(2025, 10),
         'cur_month': 10},
        template_file
    )
    write_to_file(output, output_file)
