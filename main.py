# -*- coding: utf-8 -*-

import logging
import time
from selenium import webdriver
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters
import records
import creds

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

def get_invoice_id(order_id):
    db = initdb('prod')
    rows = db.query("select payment_id, invoice_id from prod_production.mvid_sap_order_yk_payment where payment_id = " + chr(39) + str(order_id) + chr(39))
    if rows.one() is None:
        db = initdb('pilot')
        rows = db.query("select payment_id, invoice_id from pilot_production.mvid_sap_order_yk_payment where payment_id = " + chr(39) + str(order_id) + chr(39))
        rows = rows.as_dict()[0]
        return rows['invoice_id']
    else:
        rows = rows.as_dict()[0]
        return rows['invoice_id']

options = webdriver.ChromeOptions()
options.add_argument('headless')

def getOrderFromVTB(update, context):
    order_id = ''.join(context.args)
    ext_order_id = get_external_order_id(order_id)
    driver = webdriver.Chrome(creds.driver_path, options=options)
    driver.get('https://platezh.vtb24.ru/mportal/#login')
    username = driver.find_element_by_id("username-inputEl")
    username.click()
    username.send_keys(creds.vtb_login)
    password = driver.find_element_by_id("password-inputEl")
    password.click()
    password.send_keys(creds.vtb_password)
    time.sleep(1)
    submit = driver.find_element_by_id("button-1117-btnInnerEl")
    submit.click()
    time.sleep(1)
    driver.get("https://platezh.vtb24.ru/mportal/#orders/" + ext_order_id + "/history?orderNumber=" + order_id)
    time.sleep(1)
    table = driver.find_elements_by_class_name("x-grid-cell-paymentState")
    paymentStatus = table[-1].text
    update.message.reply_text(paymentStatus)
    driver.close()

def getOrderFromYK(update, context):
    order_id = ''.join(context.args)
    invoice_id = get_invoice_id(order_id)
    driver = webdriver.Chrome(creds.driver_path, options=options)
    driver.implicitly_wait(10)
    driver.get("https://passport.yandex.ru/auth?from=money&origin=merchant&retpath=https%3A%2F%2Fkassa.yandex.ru%2Fmy%2F%3Fget-auth%3Dyes")
    username = driver.find_element_by_xpath("/html/body/div/div/div/div[2]/div/div/div[2]/div[3]/div/div/div[1]/form/div[1]/span/input")
    username.click()
    username.send_keys(creds.yk_login)
    enter = driver.find_element_by_xpath("/html/body/div/div/div/div[2]/div/div/div[2]/div[3]/div/div/div[1]/form/div[3]/button")
    enter.click()
    #time.sleep(1)
    password = driver.find_element_by_xpath("/html/body/div/div/div/div[2]/div/div/div[2]/div[3]/div/div/form/div[2]/div/span/input")
    password.click()
    password.send_keys(creds.yk_password)
    #time.sleep(1)
    submit = driver.find_element_by_xpath("/html/body/div/div/div/div[2]/div/div/div[2]/div[3]/div/div/form/div[3]/button")
    submit.click()
    #time.sleep(1)
    allstores = driver.find_element_by_xpath("/html/body/div[1]/div[2]/header/div/div/div/div[2]/div[1]/div/div/div[1]/span/span[1]")
    allstores.click()
    #time.sleep(1)
    prod = driver.find_element_by_xpath("/html/body/div[1]/div[2]/header/div/div/div/div[2]/div[1]/div/div/div[2]/div/div/div[2]/div/div[2]/div[25]/div")
    prod.click()
    driver.get("https://kassa.yandex.ru/my/payments?search=" + invoice_id)
    #time.sleep(1)
    status = driver.find_elements_by_xpath("/html/body/div[1]/div[2]/div[2]/div/div/div/div[2]/div[3]/div[2]/div/div[2]/div/div[1]/div/div[3]/div/div[1]/div/div[2]/span")
    paymentStatus = status[-1].text
    update.message.reply_text(paymentStatus)
    driver.close()

def main():
    """Start the bot."""
    # Create the Updater and pass it your bot's token.
    # Make sure to set use_context=True to use the new context based callbacks
    # Post version 12 this will no longer be necessary
    updater = Updater(creds.bot_api, use_context=True)

    # Get the dispatcher to register handlers
    dp = updater.dispatcher

    # on different commands - answer in Telegram
    dp.add_handler(CommandHandler("vtb", getOrderFromVTB))
    dp.add_handler(CommandHandler("yk", getOrderFromYK))

    # on noncommand i.e message - echo the message on Telegram

    # Start the Bot
    updater.start_polling()

    # Run the bot until you press Ctrl-C or the process receives SIGINT,
    # SIGTERM or SIGABRT. This should be used most of the time, since
    # start_polling() is non-blocking and will stop the bot gracefully.
    updater.idle()


if __name__ == '__main__':
    main()