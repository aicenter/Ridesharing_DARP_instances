import setuptools
from setuptools import setup

setup(
	name='darpinstances',
	version='0.0.1',
	description='Tools to create DARP benchmark instances define the soluton format and process the results',
	author='David Fiedler',
	author_email='david.fido.fiedler@gmail.com',
	license='GNU GPLv3',
	packages=setuptools.find_packages(),
	install_requires=[
		'numpy',
		'pandas',
		'plotly',
		'tqdm',
		'typing',
		'pyyaml',
		'h5py',
		'geopandas',
		'osmnx',
		'scipy',
		'psycopg2-binary',
		'sqlalchemy',
		'geoalchemy2',
		'sshtunnel',
		'scikit-learn',
		'ssh'
	],
	python_requires='>=3.8'
)
