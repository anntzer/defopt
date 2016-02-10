from setuptools import setup


with open('README.rst') as readme:
    long_description = readme.read()


setup(
    name='defopt',
    version='0.3.1',
    description='Effortless argument parsing',
    long_description=long_description,
    author='evan_',
    author_email='evanunderscore@gmail.com',
    url='https://pypi.python.org/pypi/defopt',
    license='GNU General Public License v3',
    py_modules=['defopt'],
    test_suite='test_defopt',
    install_requires=['docutils'],
    extras_require={
        ':python_version=="2.7"': ['enum34', 'funcsigs'],
        ':python_version=="3.3"': ['enum34'],
    },
    tests_require=['coverage'],
    setup_requires=['nose'],
    classifiers=[
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.3',
        'Programming Language :: Python :: 3.4',
        'Programming Language :: Python :: 3.5',
        'License :: OSI Approved :: GNU General Public License v3 (GPLv3)',
        'Operating System :: OS Independent',
        'Development Status :: 3 - Alpha',
        'Intended Audience :: Developers',
    ],
)
