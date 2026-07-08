from abc import ABC, abstractmethod


class BaseParser(ABC):
    """
    An abstract base class for all parsers in the project.
    It ensures that every new scraper will have the same set of methods.
    """

    @abstractmethod
    async def get_data(self, url: str) -> dict:
        """
        Asynchronous method for retrieving and processing data from the specified URL.

        :param url: A link to the car's page.
        :return: A dictionary containing the retrieved data (title, price, VIN, etc.).
        """
        pass