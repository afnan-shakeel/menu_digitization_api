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

def calculate_threshold(column):
        # Extract Y-coordinates from the column items
        y_coordinates = [item['polygons'][0][1] for item in column]

        # Calculate the interquartile range (IQR) of the Y-coordinates
        q1 = np.percentile(y_coordinates, 25)
        q3 = np.percentile(y_coordinates, 75)
        iqr = q3 - q1

        # Set the threshold as a fraction of the IQR
        threshold = iqr * 0.75  # Adjust the fraction as needed

        return threshold

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
                text_data.append({
                    'text': text,
                    'polygons': polygons
                })

        return text_data

# extract dish names, prices, and associated polygons
def extract_dish_prices(text_data, price_regex):
        dish_prices = []

        for i in range(1, len(text_data)):
            current_text = text_data[i]['text']
            previous_text = text_data[i-1]['text']

            if re.match(price_regex, current_text):
                dish_name = previous_text.strip()
                price = current_text.strip()
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
            print(file)
            # Process the uploaded file as needed
            # For example, save it to a specific location
            with open(os.path.join(settings.MEDIA_ROOT, file.name), 'wb+') as destination:
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

        file_name = 'testmenu.png'
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