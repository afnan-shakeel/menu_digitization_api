from django.http import HttpResponse
import boto3
import re
import numpy as np
from operator import itemgetter
from django.http import JsonResponse
from django.conf import settings
from django.views.decorators.csrf import csrf_exempt
import os

def index(request):
    return HttpResponse("Hello, world. You're at the polls index.")

def delete_files_in_folder(folder_path):
    try:
        for filename in os.listdir(folder_path):
            file_path = os.path.join(folder_path, filename)
            if os.path.isfile(file_path):
                os.remove(file_path)
                print(f"Deleted file: {file_path}")
    except Exception as e:
        print(f"An error occurred: {e}")


def group_columns_by_categories(column_groups, threshold):
    y_group = []

    for column in column_groups:

        sorted_column = sorted(column, key=lambda x: x['polygons']['current_block'][0]['Y'])
        
        current_group = [sorted_column[0]]

        for i in range(1, len(sorted_column)):
            current_item = sorted_column[i]
            prev_item = sorted_column[i-1]

            curr_y = sorted_column[i]['polygons']['current_block'][0]['Y']
            prev_y = sorted_column[i-1]['polygons']['current_block'][0]['Y']

            if abs(curr_y - prev_y) <= threshold:
                # add the previous category to y_group
                current_group.append(current_item)

            else:
                y_group.append(current_group)
                current_group = [current_item]

        y_group.append(current_group)

    return y_group

# extract text and polygons from the image using Textract
def extract_text_and_polygons(client, file_name):
        with open(os.path.join(settings.MEDIA_ROOT, file_name), 'rb') as image_file:
            image_bytes = image_file.read()

        response = client.detect_document_text(Document={'Bytes': image_bytes})
        blocks = response['Blocks']

        text_data = []

        for block in blocks:
            if block['BlockType'] == 'LINE':
                text = block['Text']
                polygons = block['Geometry']['Polygon']
                id = block['Id']
                text_data.append({
                    'text': text,
                    'polygons': polygons,
                    'id': id
                })


        return text_data

def extract_dish_prices(text_data, price_regex):
    dish_prices = []
    i = 0
    while True:
        # print("["+str(i)+"]")
        last_element_condition = (text_data[i]['id'] == text_data[-1]['id'])

        if last_element_condition:
            break
        # if re.match(price_regex, current_text) and re.match(price_regex, current_text + 1) && re.match(price_regex, current_text) + 2 => i+=3 and to use pol of text[i+3]
        if (text_data[i]['id'] not in [text_data[-1]['id'], text_data[-2]['id'], text_data[-3]['id']]) and re.match(price_regex, text_data[i]['text']) and re.match(price_regex, text_data[i+1]['text']) and re.match(price_regex, text_data[i+2]['text']):
            dish_name = text_data[i-1]['text'].strip()
            price = [text_data[i]['text'].strip(), text_data[i+1]
                     ['text'], text_data[i+2]['text']]
            current_polygon = text_data[i]['polygons']
            previous_polygon = text_data[i-1]['polygons']
            next_polygon = text_data[i+1]['polygons']
            dish_price_obj = {
                'dish_name': dish_name,
                'price': price,
                'polygons': {
                    'current_block': current_polygon,
                    'prev_block': previous_polygon,
                    'next_block': next_polygon
                }
            }
            dish_prices.append(dish_price_obj)

            # print('matched for 3 price: ', dish_name, price)
            i += 3
            continue
        # if re.match(price_regex, current_text) and re.match(price_regex, current_text + 1) => i+=3 and to use pol of text[i+3]
        elif (text_data[i]['id'] not in [text_data[-1]['id']]) and re.match(price_regex, text_data[i]['text']) and re.match(price_regex, text_data[i+1]['text']):
            dish_name = text_data[i-1]['text'].strip()
            price = [text_data[i]['text'].strip(), text_data[i+1]['text']]
            current_polygon = text_data[i]['polygons']
            previous_polygon = text_data[i-1]['polygons']
            next_polygon = text_data[i+1]['polygons']
            dish_price_obj = {
                'dish_name': dish_name,
                'price': price,
                'polygons': {
                    'current_block': current_polygon,
                    'prev_block': previous_polygon,
                    'next_block': next_polygon
                }
            }
            dish_prices.append(dish_price_obj)

            # print('matched for 2 price: ', dish_name, price)
            i += 2
            continue

        elif re.match(price_regex, text_data[i]['text']):
            dish_name = text_data[i-1]['text'].strip()
            price = text_data[i]['text'].strip()
            current_polygon = text_data[i]['polygons']
            previous_polygon = text_data[i-1]['polygons']
            # neglecting this i (was i+1)
            next_polygon = text_data[i]['polygons']

            dish_price_obj = {
                'dish_name': dish_name,
                'price': [price],
                'polygons': {
                    'current_block': current_polygon,
                    'prev_block': previous_polygon,
                    'next_block': next_polygon
                }
            }

            dish_prices.append(dish_price_obj)
            # print('matched for 1 price: ', dish_name, price)
            i += 1

            continue
        i+=1

    return dish_prices

def group_items_within_column(text_data, threshold):

        sorted_text_data = sorted(text_data, key=lambda x: x['polygons']['current_block'][0]['X'])

        column_groups = []

        for item in sorted_text_data:
            if not column_groups:
                column_groups.append([item])
                continue

            last_item = column_groups[-1][-1]
            if abs(item['polygons']['current_block'][0]['X'] - last_item['polygons']['current_block'][0]['X']) <= threshold:
                column_groups[-1].append(item)
            else:
                column_groups.append([item])

        return column_groups

@csrf_exempt
def upload_image(request):
    if request.method == 'POST':
        if request.FILES['file']:
            file = request.FILES['file']
            # print(file)
            delete_files_in_folder(settings.MEDIA_ROOT)
            with open(os.path.join(settings.MEDIA_ROOT, 'extraction_image.png'), 'wb+') as destination:
                for chunk in file.chunks():
                    destination.write(chunk)
            
            file_url = settings.MEDIA_URL + file.name
            print('res: ', file_url)
            return JsonResponse({'file_url': file_url})
        else:
            return HttpResponse("file not found")

@csrf_exempt
def extract_process(request):

    if request.method == "GET":
        client = boto3.client('textract')

        file_name = 'extraction_image.png'
        special_strings = ['/-',':','$','₹','/=']
        global blocks
        extracted_data = extract_text_and_polygons(client=client, file_name=file_name)
        
        # remove special strings 
        filtered_data = [data for data in extracted_data if not any(special_str in data['text'] for special_str in special_strings)]

        price_regex = r'^[0-9.]*$|^[0-9.\/ 0-9.-]*$|^[₹0-9.]*$'
        dish_prices = extract_dish_prices(filtered_data, price_regex)
        column_groups = group_items_within_column(dish_prices, 0.1)
        categs = group_columns_by_categories(column_groups,0.05)
        
        result = []
        for index, categ in enumerate(categs):

            item_list = []
            for item in categ:
                item_value = {"dish_name": item['dish_name'],"price": item["price"]}
                item_list.append(item_value)
            
            categ_value = {"category": "category " + str(index+1), "data": item_list}
            result.append(categ_value)

        return JsonResponse({"message":"success", "data": result})