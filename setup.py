from setuptools import setup, find_packages

setup(
    name="photo-manager",
    version="0.1.0",
    packages=find_packages(),
    install_requires=[
        "Pillow>=9.0.0",
        "SQLAlchemy>=1.4.0",
        "PyYAML>=6.0",
        "imagehash>=4.3.0",
        "PySide2>=5.15.0",
    ],
    entry_points={
        "console_scripts": [
            "photo-manager=photo_manager.main:main",
            "photo-slideshow-pi=photo_manager.slideshow_pi:main",
        ],
    },
    python_requires=">=3.8",
)
