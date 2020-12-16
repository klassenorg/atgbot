# -*- coding: utf-8 -*-

import logging
import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from telegram.ext import Updater, CommandHandler
import records
import creds
import requests
import json 
from datetime import datetime
import re

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)
logger = logging.getLogger(__name__)

#Error handler
def error(bot, update, error):
    logger.warn('Update "%s" caused error "%s"' % (update, error))


#initiate DB
def initdb(env):
    if env == 'prod':
        database = records.Database(creds.ATGPRD)
        return database
    else:
        database = records.Database(creds.ATGPLT)
        return database
    return database

def get_external_order_id(order_id):
    db = initdb('prod')
    rows = db.query("select payment_id, external_order_id from prod_production.mvid_sap_order_vtb_payment where payment_id = " + chr(39) + str(order_id) + chr(39))
    if rows.one() is None:
        db = initdb('pilot')
        rows = db.query("select payment_id, external_order_id from pilot_production.mvid_sap_order_vtb_payment where payment_id = " + chr(39) + str(order_id) + chr(39))
        rows = rows.as_dict()[0]
        return rows['external_order_id']
    else:
        rows = rows.as_dict()[0]
        return rows['external_order_id']

yk_env = 'prod'

def get_invoice_id(order_id):
    global yk_env
    db = initdb('prod')
    rows = db.query("select payment_id, invoice_id from prod_production.mvid_sap_order_yk_payment where payment_id = " + chr(39) + str(order_id) + chr(39))
    if rows.one() is None:
        db = initdb('pilot')
        rows = db.query("select payment_id, invoice_id from pilot_production.mvid_sap_order_yk_payment where payment_id = " + chr(39) + str(order_id) + chr(39))
        rows = rows.as_dict()[0]
        yk_env = 'pilot'
        return rows['invoice_id']
    else:
        rows = rows.as_dict()[0]
        yk_env = 'prod'
        return rows['invoice_id']

options = webdriver.ChromeOptions()
options.add_argument('headless')
options.add_argument('window-size=1920,1080')

def checkOrder(order_id):
    order_id = str(order_id)
    if order_id.isdigit() is not True or len(order_id)!=10 or re.match('[17][50][1-9]*\d*', order_id) is None:
        return False
    else:
        return True


def getOrder(update, context):
    #env init
    order_id = ''.join(context.args)
    if checkOrder(order_id) is not True:
        update.message.reply_text('Неправильный номер заказа.')
        return
    env = 'prod'
    db = initdb(env)
    #check prod
    if db.query("select order_id from "+ env +"_production.mvid_sap_order where order_id = " + chr(39) + str(order_id) + chr(39)).one() is None:
        env = 'pilot'
        db = initdb(env)
        #check pilot
        if db.query("select order_id from "+ env +"_production.mvid_sap_order where order_id = " + chr(39) + str(order_id) + chr(39)).one() is None:
            update.message.reply_text('Заказа нет в БД.')
            return
    #get order info
    order = db.query("select atg_order_id, status, export_stage, creation_datetime, bips, ip_user from "+ env +"_production.mvid_sap_order where order_id = " + chr(39) + str(order_id) + chr(39)).one()
    payment = db.query("select payment_name from "+ env +"_production.mvid_sap_order_payment where payment_id = " + chr(39) + str(order_id) + chr(39)).one()['payment_name']
    #online card
    if payment == 'onlineCard':
        headers = {'Content-Type': 'application/json'}
        data = '{ "RequestBody": { "orderNumber": "' + order_id + '", "orderId": "' + get_external_order_id(order_id) + '"} }'
        response = requests.post('http://prod.sp.mvideo.ru:80/acquiring/rest/banking/payment/info/extended', headers=headers, data=data, auth=('ATG', creds.sppass))
        orderStatus = json.loads(json.dumps(json.loads(response.text)['ResponseBody']))['orderStatus']
        status = {
            0: 'Заказ зарегистрирован, но не оплачен',
            1: 'Предавторизованная сумма захолдирована (для двухстадийных платежей)',
            2: 'Проведена полная авторизация суммы заказа',
            3: 'Авторизация отменена (Только если мы сами отменили авторизацию)',
            4: 'По транзакции была проведена операция возврата',
            5: 'Инициирована авторизация через ACS банка-эмитента (клиент перенаправлен на URL сервиса ACS банка-эмитента для подтверждения платежа по технологии 3DSecure)',
            6: 'Авторизация отклонена (операцию отклонил или фрод-мониторинг, или получен отказ от эмитента(например нет денег), или ответ эмитента не получен за отведённое время)'
        }
        totalPriceAndPaymentAmount = db.query("select mso.total_price, vp.payment_amount from "+ env +"_production.mvid_sap_order mso join "+ env +"_production.mvid_sap_order_vtb_payment vp on vp.payment_id = mso.payment_id where order_id = " + chr(39) + str(order_id) + chr(39))
        if totalPriceAndPaymentAmount.one()['total_price'] is not None:
            totalPrice = str(totalPriceAndPaymentAmount.one()['total_price'])
        else: 
            totalPrice = 'null'
        if totalPriceAndPaymentAmount.one()['payment_amount'] is not None:
            paymentAmount = str(totalPriceAndPaymentAmount.one()['payment_amount']/100)
        else:
            paymentAmount = 'null'
        update.message.reply_text(
            '''
Номер заказа: {}, env: {}
ATG Order ID: {}
Status: {}
Export stage: {}
Время создания: {}
bips: {}
IP: {}
Оплата: {}
Сумма заказа: {}
Сумма оплаты: {}
Статус платежа: {}'''.format(
                order_id, env, 
                order['atg_order_id'], 
                order['status'],
                order['export_stage'],
                order['creation_datetime'].strftime("%d.%m.%y %H:%M:%S"),
                order['bips'],
                order['ip_user'],
                payment,
                totalPrice,
                paymentAmount,
                status[orderStatus]
            )
        )
    elif payment == 'yandexKassa':
        response = requests.get('https://payment.yandex.net/api/v3/payments/' + get_invoice_id(order_id), auth=(creds.yk_shop[env], creds.yk_pass[env]))
        update.message.reply_text(
            '''
Номер заказа: {}, env: {}
ATG Order ID: {}
Status: {}
Export stage: {}
Время создания: {}
bips: {}
IP: {}
Оплата: {}
Статус платежа: {}, {}'''.format(
                order_id, env, 
                order['atg_order_id'], 
                order['status'],
                order['export_stage'],
                order['creation_datetime'].strftime("%d.%m.%y %H:%M:%S"),
                order['bips'],
                order['ip_user'],
                payment,
                json.loads(response.text)['status'],
                "Оплачено" if json.loads(response.text)['paid'] else "Не оплачено"
            )
        )
    else:
        update.message.reply_text(
            '''
Номер заказа: {}, env: {}
ATG Order ID: {}
Status: {}
Export stage: {}
Время создания: {}
bips: {}
IP: {}
Оплата: {}'''.format(
                order_id, env,
                order['atg_order_id'], 
                order['status'],
                order['export_stage'],
                order['creation_datetime'].strftime("%d.%m.%y %H:%M:%S"),
                order['bips'],
                order['ip_user'],
                payment
            )
        )


def main():
    """Start the bot."""
    # Create the Updater and pass it your bot's token.
    # Make sure to set use_context=True to use the new context based callbacks
    # Post version 12 this will no longer be necessary
    updater = Updater(creds.bot_api, use_context=True)

    # Get the dispatcher to register handlers
    dp = updater.dispatcher

    # on different commands - answer in Telegram
    dp.add_handler(CommandHandler("order", getOrder))

    # on noncommand i.e message - echo the message on Telegram

    # Start the Bot
    updater.start_polling()

    # Run the bot until you press Ctrl-C or the process receives SIGINT,
    # SIGTERM or SIGABRT. This should be used most of the time, since
    # start_polling() is non-blocking and will stop the bot gracefully.
    updater.idle()


if __name__ == '__main__':
    main()