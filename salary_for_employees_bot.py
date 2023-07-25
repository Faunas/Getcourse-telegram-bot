import copy
import datetime
import functools
import re
import sqlite3
import time
from datetime import datetime

import requests
import telebot
from telebot import types

from API.secret_info import *

bot = telebot.TeleBot(TOKEN)


@bot.message_handler(commands=['start', 'help'])
def start(message):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    auth_button = types.KeyboardButton('🔑 Авторизоваться')

    markup.add(auth_button)
    bot.send_message(message.chat.id,
                     f'🤗Здравствуйте, {message.from_user.first_name}!\nПеред началом работы необходимо проверить, являетесь ли вы нашим сотрудником🫅\n\nНажмите на кнопку ниже👇',
                     reply_markup=markup)


def is_a_user(message):
    with sqlite3.connect("all_info_users.db") as con:
        cur = con.cursor()
        res = cur.execute(f"SELECT telegram_id FROM users WHERE telegram_id = {message.chat.id}")
        result = res.fetchone()
        return result[0]


def is_admin(message):
    with sqlite3.connect("all_info_users.db") as con:
        cur = con.cursor()
        res = cur.execute(f"SELECT admin FROM users WHERE telegram_id = {message.chat.id}")
        result = res.fetchone()
        return result[0]


@bot.message_handler(commands=['menu'])
def call_main_menu(message):
    if is_a_user(message):
        markup1 = types.ReplyKeyboardMarkup(resize_keyboard=True,
                                            one_time_keyboard=False)
        item2 = types.KeyboardButton('💸 Моя зарплата')
        item4 = types.KeyboardButton('📚 Мои курсы')
        if is_admin(message):
            admin_panel = types.KeyboardButton('🛠 Админ панель')
            markup1.add(item2, item4, admin_panel)
        else:
            markup1.add(item2, item4)
        bot.send_message(message.chat.id, '👉 Выберите действие:', reply_markup=markup1)
    else:
        bot.send_message(message,
                         '❌ Вы не являетесь сотрудником нашей команды!\n\nЕсли вы считаете, что это ошибка - сообщите оператору: https://t.me/CreativiTTy')

def is_valid_date_format(timedata):
    # Regular expression to match the date format (YYYY-MM-DD)
    date_format_pattern = r'^\d{4}-(0[1-9]|1[0-2])-(0[1-9]|[12]\d|30)$'
    if not re.match(date_format_pattern, timedata):
        return False

    year, month, day = map(int, timedata.split('-'))

    if month < 1 or month > 12:
        return False

    if day < 1 or day > 31:
        return False

    return True


@bot.message_handler(commands=['my_salary'])
def handle_salary_request(message):
    if is_a_user(message):
        msg = bot.send_message(message.chat.id,
                               "Введите первую дату, С которой начнётся обработка данных: \nПример: 2023-03-10",
                               reply_markup=telebot.types.ReplyKeyboardRemove())
        bot.register_next_step_handler(msg, process_salary_request_firstdata)
    else:
        bot.send_message(message.chat.id,
                         '❌ Вы не являетесь сотрудником нашей команды!\n\nЕсли вы считаете, что это ошибка - сообщите оператору: https://t.me/CreativiTTy')


#   Функция получает первую дату от пользователя и перенаправляет на другую функцию, для получения второй даты.
def process_salary_request_firstdata(message):
    first_timedata = message.text
    if not is_valid_date_format(first_timedata):
        bot.send_message(message.chat.id,
                         "Отмена операции!\nПричина: Нет соответствия формата даты.\nНапоминание: Вводить дату нужно исключительно в формате ГОД-МЕСЯЦ-ДЕНЬ\nПример: 2023-03-10")
        call_main_menu(message)
    else:
        msg = bot.send_message(message.chat.id,
                               "Введите вторую дату, ДО которой будет обработка данных: \nПример: 2023-03-10",
                               reply_markup=telebot.types.ReplyKeyboardRemove())
        bot.register_next_step_handler(msg, functools.partial(process_salary_request_lastdata,
                                                              first_timedata=first_timedata))


def process_salary_request_lastdata(message, first_timedata):
    last_timedata = message.text
    if not is_valid_date_format(last_timedata):
        bot.send_message(message.chat.id,
                         "Отмена операции!\nПричина: Нет соответствия формата даты.\nНапоминание: Вводить дату нужно исключительно в формате ГОД-МЕСЯЦ-ДЕНЬ\nПример: 2023-03-10")
        call_main_menu(message)
    else:
        create_export_id_for_my_salary(message, first_timedata, last_timedata)


def create_export_id_for_my_salary(message, first_timedata, last_timedata):
    url = f"https://{account_name}/pl/api/account/deals?key={secret_key}&created_at[from]={first_timedata}&created_at[to]={last_timedata}&status=payed"
    response = requests.get(url)
    if response.status_code == 200:
        data = response.json()
        print(data)
        if data['error_message'] == 'Уже запущен один экспорт, попробуйте позднее':
            bot.send_message(message.chat.id,
                             "Уже обрабатываются какие либо данные, повторите попытку через 2-3 минуты.")
            call_main_menu(message)
        else:
            export_id = data['info']['export_id']
            my_salary(message, export_id, firstdatetime=first_timedata, lastdatetime=last_timedata)
    else:
        print(f"Ошибка при запросе: {response.status_code} - {response.text}")
        return


tarif_counters = {
    'Аппаратная косметология': {'count': 0, 'prineseno': 0},
    '"Профи - расширенный + отработка"': {'count': 0, 'prineseno': 0},
    '"Профи - расширенный + отработка" 2022-2023': {'count': 0, 'prineseno': 0},
    '"Профи - расширенный"': {'count': 0, 'prineseno': 0},
    '"Профи - расширенный" 2022-2023': {'count': 0, 'prineseno': 0},
    '"Профи - расширенный + отработка" 2022 -2023': {'count': 0, 'prineseno': 0}
}


def my_salary(message, export_id, firstdatetime, lastdatetime):
    bot.send_message(message.chat.id,
                     "🤖📝Началась обработка данных.\nМаксимальное время ожидания 5 минут, в зависимости от очереди.\nПожалуйста, ожидайте💫")
    url = f"https://{account_name}/pl/api/account/exports/{export_id}?key={secret_key}"
    while True:
        response = requests.get(url)
        if response.status_code == 200:
            data = response.json()
            if data['error_message'] == 'Файл еще не создан ':
                time.sleep(60)
            else:
                break
        else:
            print(f"Ошибка при запросе: {response.status_code} - {response.text}")
            return
    users_data = data['info']['items']

    #   Подсчёт учеников в определенном тарифе.

    tarif_counters_default = copy.deepcopy(tarif_counters)
    for user in users_data:
        tarif = user[8]
        tarif = tarif.replace('Косметология. Тариф: ', '')
        if tarif == '"Профи - расширенный + отработка" 2022 -2023':
            money = float(user[17]) - 5000
        else:
            money = float(user[17])

        if tarif in tarif_counters_default:
            if tarif == '"Профи - расширенный + отработка"' or tarif == '"Профи - расширенный + отработка" 2022-2023':
                tarif = '"Профи - расширенный + отработка" 2022 -2023"'
            elif tarif == '"Профи - расширенный"':
                tarif = '"Профи - расширенный" 2022-2023"'
            else:
                tarif_counters_default[tarif]['count'] += 1
                tarif_counters_default[tarif]['prineseno'] += money
        else:
            print(f"Неизвестный тариф: {tarif}. Сравнение с словарём \"tarif_counters\"")

    message_to_send = f"📝Отчёт по вашему запросу [ЗАРПЛАТА]\nВременной промежуток обработки с {firstdatetime} по {lastdatetime}\n"
    total_money = 0
    for tarif, count_data in tarif_counters_default.items():
        count = count_data['count']
        money = count_data['prineseno']
        if count > 0:
            tariff_earnings = round(money * 0.2)
            total_money += tariff_earnings
            message_to_send += f"\n📍Тариф: {tarif}\n👤Количество участников: {count}\n💲Ваша зарплата: {tariff_earnings} ₽\n\n"

    bot.send_message(message.chat.id, message_to_send + f"\n✔️Итого: {total_money} ₽")
    # Удаляем копию словаря, т.к она больше не нужна
    del tarif_counters_default
    call_main_menu(message)


#   Нужно для "📚 Мои курсы"

courses_dict = {
    "Косметология": [
        '"Профи - расширенный + отработка"',
        '"Профи - расширенный + отработка" 2022-2023"',
        '"Профи - расширенный"',
        '"Профи - расширенный" 2022-2023',
        '"Профи - расширенный + отработка" 2022 -2023',
        'Аппаратная косметология'
    ]
}


def give_coursename(message):
    with sqlite3.connect("all_info_users.db") as con:
        cur = con.cursor()
        res = cur.execute(f"SELECT course_curator FROM users WHERE telegram_id = {message.chat.id}")
        result = res.fetchone()
        if result:
            course_curator = result[0]
            return course_curator


@bot.message_handler(commands=['my_courses'])
def my_courses(message):
    with sqlite3.connect("all_info_users.db") as con:
        cur = con.cursor()
        res = cur.execute(f"SELECT course_curator FROM users WHERE telegram_id = {message.chat.id}")
        result = res.fetchone()

        if result:
            course_curator = result[0]
            if course_curator == "Косметология":  # Check if the course curator is "Косметология"
                required_courses = [
                    '"Профи - расширенный" 2022-2023',
                    '"Профи - расширенный + отработка" 2022 -2023',
                    'Аппаратная косметология'
                ]
                filtered_courses = [
                    course for course in courses_dict[course_curator] if course in required_courses
                ]
                courses_text = "\n".join(filtered_courses)
                bot.send_message(message.chat.id,
                                 f"👑Вы куратор направления \"{course_curator}\".\n✅Ваши курсы:\n{courses_text}")
            else:
                bot.send_message(message.chat.id,
                                 f"👑Вы куратор направления \"{course_curator}\", но у вас нет соответствующих курсов.")
        else:
            bot.send_message(message.chat.id, "❌Вы не являетесь куратором ни одного направления.")


def all_info_about_teachers(message):
    user_info_list = []
    with sqlite3.connect("all_info_users.db") as con:
        cur = con.cursor()
        res = cur.execute("SELECT telegram_id, user_name, course_curator FROM users")
        for telegram_id, user_name, course_curator in res.fetchall():
            user_info = f"ID: {telegram_id} | Имя: {user_name} | Направление: {course_curator}"
            user_info_list.append(user_info)
            print(user_info)
        if not user_info_list:
            user_info_list.append("No users found.")
    message_text = "Список преподавателей:\n" + "\n".join(user_info_list)
    bot.send_message(message.chat.id, message_text)


def add_teacher(message):
    bot.send_message(message.chat.id, "Введите telegram_id преподавателя:",
                     reply_markup=telebot.types.ReplyKeyboardRemove())
    bot.register_next_step_handler(message, get_telegram_id)


def get_telegram_id(message):
    telegram_id = message.text

    bot.send_message(message.chat.id, "Введите имя преподавателя:")
    bot.register_next_step_handler(message, get_user_name, telegram_id)


def get_user_name(message, telegram_id):
    user_name = message.text

    bot.send_message(message.chat.id, "Введите направление преподавателя:")
    bot.register_next_step_handler(message, get_course_curator, telegram_id, user_name)


def get_course_curator(message, telegram_id, user_name):
    course_curator = message.text

    # После получения всех данных, добавляем преподавателя в базу данных
    with sqlite3.connect("all_info_users.db") as con:
        cur = con.cursor()
        cur.execute(
            f"INSERT INTO users (`id`, `telegram_id`, `user_name`, `course_curator`, `admin`) VALUES (NULL, '{telegram_id}', '{user_name}', '{course_curator}', '0')"
        )
        con.commit()

    bot.send_message(message.chat.id, "Преподаватель успешно добавлен.")
    all_info_about_teachers(message)
    call_main_menu(message)


def delete_teacher(message):
    id_prepoda = message.text
    with sqlite3.connect("all_info_users.db") as con:
        cur = con.cursor()
        try:
            cur.execute(f"DELETE FROM users WHERE telegram_id = {id_prepoda}")
            bot.send_message(message.chat.id, "Преподаватель успешно удалён!")
        except:
            print(f"Препода с таким айди нет в базе данных. ({id_prepoda})")
            bot.send_message(message.chat.id, "Преподавателя с таким айди нет в базе данных!")
    all_info_about_teachers(message)
    call_main_menu(message)


@bot.message_handler(content_types=['text'])
def bot_message(message):
    if message.chat.type == 'private':
        if message.text == '🔑 Авторизоваться':
            if is_a_user(message):
                bot.send_message(message.chat.id, '✅ Успешная авторизация!')
                call_main_menu(message)
            else:
                print(message.chat.id)
                bot.send_message(message.chat.id,
                                 '❌ Вы не являетесь сотрудником нашей команды!\n\nЕсли вы считаете, что это ошибка - сообщите оператору: https://t.me/CreativiTTy')
        elif message.text == '💸 Моя зарплата' and is_a_user(message):
            handle_salary_request(message)
        elif message.text == '📚 Мои курсы' and is_a_user(message):
            my_courses(message)
        elif message.text == '🛠 Админ панель' and is_admin(message):
            markup1 = types.ReplyKeyboardMarkup(resize_keyboard=True)
            item2 = types.KeyboardButton('Добавить преподавателя')
            item3 = types.KeyboardButton('Удалить преподавателя')
            item4 = types.KeyboardButton('Список преподавателей')
            back = types.KeyboardButton('Вернуться в меню')
            markup1.add(item2, item3, item4, back)
            bot.send_message(message.chat.id, 'Вы вошли в Админ. Панель.', reply_markup=markup1)
        elif message.text == "Вернуться в меню" and is_a_user(message):
            call_main_menu(message)
        elif message.text == "Добавить преподавателя" and is_admin(message):
            add_teacher(message)
        elif message.text == "Удалить преподавателя" and is_admin(message):
            all_info_about_teachers(message)
            msg = bot.send_message(message.chat.id, "Введите айди преподавателя: ",
                                   reply_markup=telebot.types.ReplyKeyboardRemove())
            bot.register_next_step_handler(msg, delete_teacher)
        elif message.text == "Список преподавателей" and is_admin(message):
            all_info_about_teachers(message)


bot.polling(none_stop=True)
