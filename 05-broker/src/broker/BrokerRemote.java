package broker;

import java.rmi.Remote;
import java.rmi.RemoteException;

public interface BrokerRemote extends Remote {
    void serverRegistered(String saleId, String serverHost, int serverPort, int expectedClients) throws RemoteException;

    void clientConnected(String saleId, String clientId, int buyers) throws RemoteException;

    void serverFinished(String saleId, String summary) throws RemoteException;

    BrokerSnapshot getSnapshot() throws RemoteException;
}
