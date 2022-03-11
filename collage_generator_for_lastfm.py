import requests
import shutil
import os
import math
import time
import json
import argparse
from glob import glob
from io import BytesIO
from subprocess import call
from PIL import Image, ImageFile, TiffImagePlugin, TiffTags
from PIL.ExifTags import TAGS
from PIL.TiffImagePlugin import ImageFileDirectory_v2

ImageFile.LOAD_TRUNCATED_IMAGES = True  # Enable force loading of janky images

clear_command = 'clear' if os.name == 'posix' else 'cls'


def Continue(message, ignore_warnings):
	if not ignore_warnings:
		result = input('Warning: ' + message + '. Continue anyway? (Y/n) > ').upper()

		if result == 'N':
			print('Alrighty. Quitting now')
			raise SystemExit

		elif result != 'Y':
			print('Invalid input. Please enter Y or N')
			Continue(message, ignore_warnings)


def ParseInputOptions():
	descriptions = {
	    'user': 'The Last.fm user to get favorite albums of. This is required',
	    'width': 'The width of the output image (in pixels). This is required',
	    'height': 'The height of the output image (in pixels). This is required',
	    'size': 'The height and width of each album cover (in pixels). Default: 300',
	    'apikey':
	    'Your API key for Last.fm. It is recommended to put your API key in apikey.txt instead of passing it as an argument. An API key is required for this program to work',
	    'output': 'The filename of the output image. The file extension doesn\'t have to be included. Default: collage',
	    'filetype': 'The filetype of the output image. Default: jpg',
	    'jpeg_quality':
	    'The quality of the output image (when using JPEG). Higher values look better but produce a larger file size. Default: 100',
	    'png_compression':
	    'The compression level of the output image (when using PNG). Higher values take longer to process but produce a smaller file size. Default: 9',
	    'period': 'The period from which to fetch favorite albums. Default: forever',
	    'layout':
	    'The layout of albums in the output image. Spiral places the top albums in the center and less popular albums near the edges using a spiral pattern. Topleft places images column by column, starting from the top-left corner. Default: topleft',
	    'update_images':
	    'Whether to fetch updated albums and images from the server. Auto only updates the images if settings are changed or if the downloaded images are over a week old. Default: auto',
	    'ignore_warnings': 'Ignore all warnings and proceed using default values'
	}
	parser = argparse.ArgumentParser(description='Generate album cover collages from your top albums on Last.fm')
	parser.add_argument('user', help=descriptions['user'])
	parser.add_argument('width', help=descriptions['width'], type=int)
	parser.add_argument('height', help=descriptions['height'], type=int)
	parser.add_argument('--size', '-s', help=descriptions['size'], type=int, default=300)
	parser.add_argument('--apikey', '-k', help=descriptions['apikey'])
	parser.add_argument('--output', '-o', help=descriptions['output'], default='collage')
	parser.add_argument('--filetype', '-f', help=descriptions['filetype'], choices=['jpg', 'png'], default='jpg')
	parser.add_argument('--jpeg_quality',
	                    '-q',
	                    help=descriptions['jpeg_quality'],
	                    type=int,
	                    default=100,
	                    metavar='{1-100}')
	parser.add_argument('--png_compression',
	                    '-c',
	                    help=descriptions['png_compression'],
	                    type=int,
	                    default=9,
	                    metavar='{0-9}')
	parser.add_argument('--period',
	                    '-p',
	                    help=descriptions['period'],
	                    choices=['forever', 'year', '6month', '3month', 'month', 'week'],
	                    default='forever')
	parser.add_argument('--layout', '-l', help=descriptions['layout'], choices=['spiral', 'topleft'], default='topleft')
	parser.add_argument('--update_images',
	                    '-u',
	                    help=descriptions['update_images'],
	                    choices=['auto', 'yes', 'no'],
	                    default='auto')
	parser.add_argument('--ignore_warnings', '-i', help=descriptions['ignore_warnings'], action='store_true')
	args = parser.parse_args()

	# Use this username as an example
	if args.user == 'example':
		args.user = 'jerboa88'

	# Check width and height
	dim = [args.width, args.height]
	dim_labels = ['width', 'height']

	for i in range(len(dim)):
		if dim[i] > 9999:
			if dim[i] > 99999:
				raise ValueError(
				    'The ' + dim_labels[i] +
				    ' entered is way too big. If you\'re serious about this you can modify the code to bypass this limitation')

			Continue('The ' + dim_labels[i] + ' entered is pretty big. This may take a while', args.ignore)

		elif dim[i] < 0:
			raise ValueError('The ' + dim_labels[i] + ' can\'t be negative')

	# Check API key
	if args.apikey:
		if len(args.apikey) != 32:
			raise ValueError('The entered API key is invalid. It must be 32 characters long')

	else:
		if os.path.exists('apikey.txt'):
			try:
				args.apikey = open('apikey.txt', 'r').read(32)

			except OSError:
				raise Exception('apikey.txt could not be read')

		else:
			raise Exception(
			    'apikey.txt does not exist. Please put your Last.fm key in apikey.txt or pass it as a command line argument')

	# Check size
	if args.size > 300:
		Continue('Most album covers are not larger than 300px so the images may look blurry', args.ignore)

	elif args.size < 32:
		if args.size < 0:
			raise ValueError('The size can\'t be negative')

		Continue('The album size is set very small', args.ignore)

	# Check period
	period_mapping = {
	    'forever': 'overall',
	    'year': '12month',
	    '6month': '6month',
	    '3month': '3month',
	    'month': '1month',
	    'week': '7day'
	}

	args.period = period_mapping[args.period]

	# Check filename
	included_extension = args.output[-4:].lower()

	if included_extension != '.png' and included_extension != '.jpg':
		args.output = args.output + '.' + args.filetype

	# Check filetype
	filetype_mapping = {'jpg': 'JPEG', 'png': 'PNG'}

	args.filetype = filetype_mapping[args.filetype]

	# Check JPEG quality
	if args.jpeg_quality > 100:
		raise ValueError('JPEG quality cannot be greater than 100')

	elif args.jpeg_quality < 32:
		if args.jpeg_quality < 1:
			raise ValueError('JPEG quality cannot be less than 1')

		Continue('The JPEG quality is set very low', args.ignore)

	# Check PNG compression
	if args.png_compression > 9:
		raise ValueError('PNG compression cannot be greater than 9')

	elif args.png_compression < 0:
		raise ValueError('PNG compression cannot be less than 0')

	# Check update images
	update_images_mapping = {'auto': 'auto', 'yes': True, 'no': False}

	args.update_images = update_images_mapping[args.update_images]

	return args


def PrintStatus(label, i, images_required):
	_ = call(clear_command)  # Clear console before printing new values
	print(label, i, '/', images_required, ' (', round(i * 100 / images_required, 1), '%)', sep='')


def GenerateSpiral(rows, cols):
	min_row = 0
	max_row = rows - 1
	min_col = 0
	max_col = cols - 1
	result = []

	while min_row <= max_row and min_col <= max_col:
		for i in range(min_col, max_col + 1):
			result.append((min_row, i))

		min_row += 1

		for i in range(min_row, max_row + 1):
			result.append((i, max_col))

		max_col -= 1

		if min_row <= max_row:
			for i in range(max_col, min_col - 1, -1):
				result.append((max_row, i))

		max_row -= 1

		if min_col <= max_col:
			for i in range(max_row, min_row - 1, -1):
				result.append((i, min_col))

		min_col += 1

	return result


def GenerateExif():
	_TAGS_r = dict(((v, k) for k, v in TAGS.items()))
	ifd = ImageFileDirectory_v2()
	ifd[_TAGS_r['Software']] = u'Last.fm Album Collage Generator by jerboa88'
	out = BytesIO()
	ifd.save(out)

	return b'Exif\x00\x00' + out.getvalue()


def CreateCollage(dimensions, rows, cols, image_size, layout, images_required, output_filename, output_filetype,
                  jpeg_quality, png_compression, ignore_warnings):
	new_im = Image.new('RGB', (dimensions[0], dimensions[1]))
	tiles = []

	print('Loading images')

	for img_path in glob('images/*.jpg'):
		tiles.append(Image.open(img_path).resize((image_size, image_size), resample=Image.BICUBIC))

	starting_y = int(-(image_size * rows - dimensions[1]) / 2)

	x = int(-(image_size * cols - dimensions[0]) / 2)
	y = starting_y

	if layout == 'spiral':
		coords = GenerateSpiral(rows, cols)
		i = images_required - 1

		for coord in coords:
			new_im.paste(tiles[i], (x + coord[1] * image_size, y + coord[0] * image_size))
			i -= 1
			PrintStatus('Processing image ', images_required - 1 - i, images_required)

	else:
		i = 0

		while x < dimensions[0]:
			while y < dimensions[1]:
				PrintStatus('Processing image ', i + 1, images_required)
				new_im.paste(tiles[i], (x, y))
				i += 1
				y += image_size

			x += image_size
			y = starting_y

	if os.path.exists(output_filename):
		Continue('The output image exists already and will be overwritten', ignore_warnings)

	new_im.save(output_filename,
	            output_filetype,
	            quality=jpeg_quality,
	            compress_level=png_compression,
	            subsampling=0,
	            exif=GenerateExif())
	print('Saved as ' + output_filename)


def CheckResponse(data):
	if data['error']:
		raise Exception('Error while fetching albums: ' + data['message'])


def CheckMeta(update_images, start_time, user, period, images_required):
	# Create images directory if it doesn't exist
	try:
		os.mkdir('images/')
		print('Created images directory')

	except OSError:
		if not os.path.isdir('images/'):
			raise Exception('Images directory could not be created')

	else:
		print('Successfully created images directory')

	# See if we need to update images
	if update_images == 'auto':
		if os.path.exists('images/meta.txt'):
			try:
				with open('images/meta.txt') as file:
					data = json.load(file)

					if data['user'] != user or data['period'] != period or data[
					    'images_fetched'] < images_required or data['time'] + 604800 <= start_time:
						return True

					else:
						return False

			except OSError:
				raise Exception('images/meta.txt could not be read')

		else:
			return True

	else:
		return update_images


def SaveMeta(start_time, user, period, images_fetched):
	data = {'time': int(start_time), 'user': user, 'period': period, 'images_fetched': images_fetched}

	with open('images/meta.txt', 'w') as file:
		json.dump(data, file)


def PrintPlural(val, label):
	print(int(val), end=' ' + label)

	if val > 1:
		print('s', end='')


def PrintTime(start_time):
	minutes, seconds = divmod(time.time() - start_time, 60)
	hours, minutes = divmod(minutes, 60)

	print('Finished in ', end='')

	if hours > 0:
		PrintPlural(hours, 'hour')
		print(', ', end='')
		PrintPlural(minutes, 'minute')
		print(', and ', end='')

	elif minutes > 0:
		PrintPlural(minutes, 'minute')
		print(' and ', end='')

	PrintPlural(seconds, 'second')
	print()


def RemoveImages():
	print('Removing old images')

	for img_path in glob('images/*.jpg'):
		if os.path.exists(img_path):
			os.remove(img_path)

		else:
			print('Can\'t remove old image. The file is missing somehow')


def main():
	start_time = time.time()
	args = ParseInputOptions()

	ignore_warnings = args.ignore_warnings  # Set ignore warnings flag first
	user = args.user  # Set global user variable
	dimensions = [args.width, args.height]
	api_key = args.apikey
	image_size = args.size
	output_filename = args.output
	output_filetype = args.filetype
	jpeg_quality = args.jpeg_quality
	png_compression = args.png_compression
	layout = args.layout
	period = args.period

	# image_number = 0 # Let users pick by number of images as well
	# image_padding = 0

	cols = math.ceil(dimensions[0] / image_size)
	rows = math.ceil(dimensions[1] / image_size)
	images_required = rows * cols
	albums = []

	if CheckMeta(args.update_images, start_time, user, period, images_required):
		print('Fetching favorite albums from Last.fm')

		page = 1
		# images_downloaded = 0
		images_queue = images_required
		page_size = min(int(images_required * 1.5), 1000)

		while images_queue > 0:
			response = requests.get('http://ws.audioscrobbler.com/2.0/?method=user.gettopalbums&format=json', {
			    'user': user,
			    'api_key': api_key,
			    'period': period,
			    'limit': page_size,
			    'page': page
			})

			data = response.json()

			if response.status_code != 200:
				CheckResponse(data)

			albums.extend(data['topalbums']['album'])

			page += 1
			images_queue -= page_size

		# albums = data['topalbums']['album']
		# input(albums)
		images_fetched = len(albums)

		print('Done')

		if images_fetched < images_required:
			raise Exception('Not enough images were fetched from the server. You may need to pick a larger date range')

		RemoveImages()

		i = 0
		image_counter = 0  # Keep track of the actual number of images downloaded
		images = []
		session = requests.Session()

		while (image_counter < images_required and i < images_fetched):
			image_url = albums[i]['image'][3]['#text']

			if image_url:
				extension = image_url[-3:]

				PrintStatus('Fetching image ', image_counter + 1, images_required)
				r = session.get(image_url, stream=True)
				local_file = open('images/' + str(image_counter).zfill(5) + '.' + extension,
				                  'wb')  # Open a local file with write binary permission
				r.raw.decode_content = True  # Set decode_content value to True, otherwise the downloaded image file's size will be zero
				shutil.copyfileobj(r.raw, local_file)  # Copy the response stream raw data to local image file
				del r  # Remove the image url response object

				image_counter += 1

				images.append(extension)

			i += 1

		SaveMeta(start_time, user, period, images_fetched)
		print('Done')

		for i in range(len(images)):
			extension = images[i]

			if extension == 'png' or extension == 'gif' or extension == 'jpeg':
				PrintStatus('Converting image ', i + 1, images_required)

				old_image_path = 'images/' + str(i).zfill(5) + '.' + extension
				new_image_path = 'images/' + str(i).zfill(5) + '.jpg'

				current_img = Image.open(old_image_path)
				current_img.convert('RGB').save(new_image_path, 'JPEG', quality=100, subsampling=0)
				current_img.close()

				if os.path.exists(old_image_path):
					os.remove(old_image_path)

				else:
					print('Can\'t remove old image. The file is missing somehow')

		print('Done')

	CreateCollage(dimensions, rows, cols, image_size, layout, images_required, output_filename, output_filetype,
	              jpeg_quality, png_compression, ignore_warnings)
	PrintTime(start_time)


main()
